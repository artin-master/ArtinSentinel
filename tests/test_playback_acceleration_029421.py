"""Offline media tests: SDK fixture contains no sockets; only pipes/local FFmpeg."""
import subprocess,time
from pathlib import Path
import pytest
from test_intelbras_cloud_bridge_pilot import sdk


def test_cloud_speed_command_reaches_native_sdk_without_live_network(sdk,monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    payload=sdk/'gray.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=gray:s=160x90:r=10','-t','12','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00'
    session=IntelbrasCloudLiveSession(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=sdk,playback=True,playback_speed=8)
    try:
        session.start();deadline=time.monotonic()+5
        while not session.frame_count and time.monotonic()<deadline:time.sleep(.02)
        assert session.frame_count>0,session.drain_diagnostics()
        assert session.effective_playback_speed==8
    finally:session.stop();assert session.wait_closed(5)
    assert 'speed=3' in (sdk/'trace').read_text()


def test_native_acceleration_advances_picture_while_bounding_output_fps(sdk,monkeypatch):
    from datetime import datetime
    from artin_sentinel.intelbras_local_playback import IntelbrasLocalPlaybackSession,local_playback_route
    from artin_sentinel.live import FRAME_WIDTH,FRAME_HEIGHT
    monkeypatch.setenv('FAKE_EXPECT_MODE','0')
    payload=sdk/'counter.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',"nullsrc=s=160x90:r=10,geq=lum='N+20':cb=128:cr=128",'-t','24','-c:v','mpeg2video','-q:v','2','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    url=local_playback_route('127.0.0.1',55162,1,datetime(2026,10,19,8),datetime(2026,10,19,9))
    session=IntelbrasLocalPlaybackSession(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=sdk,playback=True,playback_speed=4,fps=10)
    try:
        session.start();deadline=time.monotonic()+5;first=None
        while first is None and time.monotonic()<deadline:first=session.latest_frame();time.sleep(.02)
        assert first is not None,session.drain_diagnostics()
        count=session.frame_count;start=time.monotonic();samples=[]
        while time.monotonic()-start<1.8:
            frame=session.latest_frame()
            if frame:samples.append(frame.pixels[(FRAME_HEIGHT//2*FRAME_WIDTH+FRAME_WIDTH//2)*3])
            time.sleep(.04)
        assert samples[-1]-samples[0]>40, samples  # Content advances >4 media seconds.
        assert session.frame_count-count<35  # Not ~72 RAW frames scaled/output for 4x.
        assert session.playback_position_seconds>4
    finally:session.stop();assert session.wait_closed(5)


def test_media_clock_measures_delivered_time_not_requested_wall_rate():
    from artin_sentinel.playback_clock import PlaybackClock
    now=[0.0];clock=PlaybackClock(4,now=lambda:now[0])
    clock.update('out_time_us=0');now[0]=2
    clock.update('out_time_us=500000')
    assert clock.position==2 and clock.rate==1
    now[0]=20
    assert clock.position==2 and clock.rate==0


def test_fast_audio_is_explicitly_paused_without_changing_listen_preference():
    from types import SimpleNamespace as NS
    from artin_sentinel.app import MainWindow
    messages=[]
    host=NS(stop_playback_audio=lambda:None,playback_listen_check=NS(isChecked=lambda:True),
            playback_audio_muted=NS(isChecked=lambda:False),playback_audio_volume=NS(value=lambda:75),
            playback_speed_combo=NS(currentData=lambda:4),playback_audio_status=NS(setText=messages.append))
    MainWindow.toggle_playback_audio(host)
    assert messages and '1×' in messages[-1] and host.playback_listen_check.isChecked()


def test_rejected_cloud_acceleration_stops_after_one_login(sdk,monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    payload=sdk/'bytes';payload.write_bytes(b'x'*188)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload));monkeypatch.setenv('FAKE_SCENARIO','speed_rejected')
    session=IntelbrasCloudLiveSession('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=sdk,playback=True,playback_speed=4)
    try:
        session.start()
        assert session.wait_closed(4),session.drain_diagnostics()
        assert session.current_state=='unavailable'
    finally:session.stop();session.wait_closed(4)
    assert (sdk/'trace').exists(),session.drain_diagnostics()
    assert (sdk/'trace').read_text().splitlines().count('login')==1

_APP=None

def test_cloud_selector_is_enabled_and_speed_change_reopens_current_position(tmp_path):
    global _APP
    from types import SimpleNamespace as NS
    from PySide6.QtWidgets import QApplication,QComboBox,QListWidget,QPushButton,QLabel
    from artin_sentinel.app import MainWindow
    from artin_sentinel.db import Database
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    _APP=QApplication.instance() or QApplication([])
    db=Database(tmp_path/'db')
    did=register_bridge_inventory(db,db.list_sites()[0]['id'],'Cloud','TEST-SERIAL-PRIVATE',37777,4,managed=True)
    host=NS(db=db,playback_device_combo=QComboBox(),playback_channel_combo=QComboBox(),
            playback_channel_list=QListWidget(),playback_web_button=QPushButton(),playback_search_btn=QPushButton(),
            playback_access_note=QLabel(),playback_speed_combo=QComboBox(),clear_playback_results=lambda:None,_device_web_services=lambda _:[])
    host.playback_device_combo.addItem('Cloud',did)
    host.playback_speed_combo.addItem('1×',1);host.playback_speed_combo.addItem('4×',4);host.playback_speed_combo.setCurrentIndex(1)
    MainWindow.refresh_playback_channels(host)
    assert host.playback_speed_combo.isEnabled() and host.playback_speed_combo.currentData()==4
    calls=[];host.playback_session=object();host.playback_clip_bounds=(1,2);host.seek_playback_stream=lambda **kw:calls.append(kw)
    MainWindow.change_playback_speed(host)
    assert calls==[{'force_reopen':True}]

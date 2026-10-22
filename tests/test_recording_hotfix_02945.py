from types import SimpleNamespace
from datetime import datetime
import pytest
from PySide6.QtWidgets import QApplication,QComboBox,QListWidget,QLabel,QPushButton
from artin_sentinel.db import Database
from artin_sentinel.app import MainWindow
from artin_sentinel.intelbras_cloud import register_bridge_inventory


def test_cloud_search_is_enabled_without_web_before_and_after_query(tmp_path):
    app=QApplication.instance() or QApplication([])
    db=Database(tmp_path/'db');did=register_bridge_inventory(db,db.list_sites()[0]['id'],'Cloud','TEST-SERIAL-PRIVATE',37777,4,managed=True)
    host=SimpleNamespace(db=db,playback_device_combo=QComboBox(),playback_channel_combo=QComboBox(),playback_channel_list=QListWidget(),playback_web_button=QPushButton(),playback_search_btn=QPushButton(),playback_access_note=QLabel(),clear_playback_results=lambda:None,_device_web_services=lambda _:[])
    host.playback_device_combo.addItem('Cloud',did)
    MainWindow.refresh_playback_channels(host)
    assert host.playback_search_btn.isEnabled(),host.playback_access_note.text()
    assert not host.playback_web_button.isEnabled()
    MainWindow.playback_search_finished(host)
    assert host.playback_search_btn.isEnabled()


def test_intelbras_local_recording_route_uses_native_speed_transport(tmp_path,monkeypatch):
    from artin_sentinel.intelbras_local_playback import local_playback_route,IntelbrasLocalPlaybackSession
    from artin_sentinel.live import create_live_stream_session
    url=local_playback_route('192.0.2.1',37777,1,datetime(2026,10,19,8),datetime(2026,10,19,9))
    session=create_live_stream_session(url,'u','p',playback=True,playback_speed=4)
    assert isinstance(session,IntelbrasLocalPlaybackSession)
    assert session.playback_speed==4
    command=session._command(url)
    assert command[command.index('-readrate')+1]=='4' and 'pipe:0' in command


@pytest.mark.parametrize('speed,expected',[(0.5,-1),(2,1),(4,2),(8,3),(16,4)])
def test_local_sdk_receives_real_speed_enum(tmp_path,monkeypatch,speed,expected):
    import subprocess,time
    from pathlib import Path
    from artin_sentinel.intelbras_local_playback import local_playback_route
    from artin_sentinel.live import create_live_stream_session
    sdk=tmp_path/'sdk';sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    monkeypatch.setenv('FAKE_TRACE',str(sdk/'trace'));monkeypatch.setenv('FAKE_EXPECT_HOST','192.0.2.1');monkeypatch.setenv('FAKE_EXPECT_MODE','0')
    payload=tmp_path/'clip.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=160x90:r=10','-t','1','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    url=local_playback_route('192.0.2.1',55162,1,datetime(2026,10,19,8),datetime(2026,10,19,9))
    session=create_live_stream_session(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',playback=True,playback_speed=speed,sdk_dir=sdk)
    try:
        session.start();frame=None;deadline=time.monotonic()+8
        while frame is None and time.monotonic()<deadline:frame=session.latest_frame();time.sleep(.02)
        assert frame is not None,session.drain_diagnostics()
        assert session.effective_playback_speed==speed
    finally:session.stop();assert session.wait_closed(5)
    # Playback stop retains login now; expiry must still perform native cleanup.
    from artin_sentinel.playback_session_pool import playback_pool
    pool=playback_pool()
    with pool.condition:entries=list(pool.entries.items())
    for key,(client,busy,_timer) in entries:
        if key[4]==str(sdk.resolve()) and not busy:pool.expire(key,client)
    trace=(sdk/'trace').read_text()
    assert f'speed={expected}' in trace and 'playback_stop' in trace and 'cleanup' in trace


def test_ui_uses_sdk_only_for_accelerated_intelbras_preview_and_keeps_rtsp_export(tmp_path,monkeypatch):
    from artin_sentinel.domain import Device,DeviceKind
    from artin_sentinel.recording_search import Recording
    app=QApplication.instance() or QApplication([])
    db=Database(tmp_path/'db');did=db.upsert_device(Device(site_id=db.list_sites()[0]['id'],name='Local',ip='192.0.2.1',kind=DeviceKind.DVR,provider='intelbras'))
    sdk=tmp_path/'sdk';sdk.mkdir();(sdk/'libdhnetsdk.so').write_bytes(b'test presence')
    monkeypatch.setenv('ARTIN_SENTINEL_NETSDK_DIR',str(sdk))
    host=SimpleNamespace(db=db,playback_device_combo=QComboBox(),playback_speed_combo=QComboBox())
    host.playback_device_combo.addItem('Local',did);host.playback_speed_combo.addItem('1x',1.0);host.playback_speed_combo.addItem('4x',4.0)
    begin,end=datetime(2026,10,19,8),datetime(2026,10,19,9)
    row=Recording(1,str(begin),str(end),'Normal',1)
    assert MainWindow.recording_route(host,row,'http://192.0.2.1',1,begin,end,554).startswith('rtsp:')
    host.playback_speed_combo.setCurrentIndex(1)
    assert MainWindow.recording_route(host,row,'http://192.0.2.1',1,begin,end,554).startswith('intelbras-sdk:')
    assert MainWindow.recording_route(host,row,'http://192.0.2.1',1,begin,end,554,native=False).startswith('rtsp:')


def test_missing_web_still_blocks_local_http_search(tmp_path):
    from artin_sentinel.domain import Device,DeviceKind
    app=QApplication.instance() or QApplication([])
    db=Database(tmp_path/'db');did=db.upsert_device(Device(site_id=db.list_sites()[0]['id'],name='Local',ip='192.0.2.1',kind=DeviceKind.DVR,provider='intelbras'))
    host=SimpleNamespace(db=db,playback_device_combo=QComboBox(),playback_channel_combo=QComboBox(),playback_channel_list=QListWidget(),playback_web_button=QPushButton(),playback_search_btn=QPushButton(),playback_access_note=QLabel(),clear_playback_results=lambda:None,_device_web_services=lambda _:[])
    host.playback_device_combo.addItem('Local',did)
    MainWindow.refresh_playback_channels(host)
    assert not host.playback_search_btn.isEnabled()


def test_local_audio_factory_routes_sdk_and_applies_tempo(monkeypatch):
    from artin_sentinel.intelbras_local_playback import local_playback_route,IntelbrasLocalPlaybackAudio
    from artin_sentinel.live import create_live_audio_session
    import artin_sentinel.intelbras_cloud_audio as audio
    monkeypatch.setattr(audio,'ffmpeg_audio_output_devices',lambda:{'pulse'})
    route=local_playback_route('192.0.2.1',37777,1,datetime(2026,10,19,8),datetime(2026,10,19,9))
    session=create_live_audio_session(route,'u','p',playback=True,playback_speed=4)
    assert isinstance(session,IntelbrasLocalPlaybackAudio)
    command=session._commands()[0][1]
    assert command[command.index('-af')+1].startswith('atempo=2,atempo=2,')
    assert session._sdk_options(route)=={'host':'192.0.2.1','login_mode':0}


from test_intelbras_cloud_bridge_pilot import sdk


def test_rejected_native_speed_is_reported_and_sdk_is_cleaned_up(sdk,tmp_path,monkeypatch):
    import os,time
    from artin_sentinel.intelbras_cloud import BridgeProcess
    payload=tmp_path/'bytes';payload.write_bytes(b'x'*188)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload));monkeypatch.setenv('FAKE_EXPECT_HOST','192.0.2.1');monkeypatch.setenv('FAKE_EXPECT_MODE','0');monkeypatch.setenv('FAKE_SCENARIO','speed_rejected')
    read,write=os.pipe();client=None
    try:
        client=BridgeProcess(55162,'','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=sdk,media_fd=write,host='192.0.2.1',login_mode=0,playback_window={'start':'2026-10-19T08:00:00','end':'2026-10-19T09:00:00'},playback_speed=4)
        deadline=time.monotonic()+3
        while client.process.poll() is None and time.monotonic()<deadline:client.poll_events();time.sleep(.02)
        client.close()
        stages=[item['stage'] for item in client.events]
        assert client.process.returncode==16
        assert 'playback_speed_failed' in stages and 'playback_speed_applied' not in stages
        assert 'cleanup_returned' in stages
    finally:
        if client:client.close()
        os.close(read);os.close(write)

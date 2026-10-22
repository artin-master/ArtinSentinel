"""Native IPC test with synthetic SDK; no DVR or network access."""
import os,subprocess,time
from pathlib import Path
from test_persistent_playback_029422 import persistent_sdk,consume_pipe,wait_stage

def test_seek_retargets_media_without_reopening_handle(persistent_sdk):
    from artin_sentinel.intelbras_cloud import BridgeProcess
    # The fake validates the exact 64-bit playback handle and the seek ABI.
    source=(persistent_sdk/'fake.cpp').read_text()+'''\nextern "C" int CLIENT_SeekPlayBackByTime(long h,NetTime* t){if(h!=0x23456789aL || t->minute!=20)std::_Exit(102);trace("seek");return scenario("seek_rejected")?0:1;}\n'''
    (persistent_sdk/'fake.cpp').write_text(source)
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(persistent_sdk/'fake.cpp'),'-o',str(persistent_sdk/'libdhnetsdk.so')],check=True)
    write,data,thread=consume_pipe();write2,data2,thread2=consume_pipe();client=None
    try:
        client=BridgeProcess(55162,'TEST-SERIAL-PRIVATE','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=persistent_sdk,media_fd=write,playback_window={'start':'2026-10-19T08:00:00','end':'2026-10-19T09:00:00'},persistent=True)
        os.close(write);write=-1;wait_stage(client,'stream_data_received')
        client.retarget_playback(write2,at='2026-10-19T08:20:00',speed=8,ident=1)
        os.close(write2);write2=-1
        wait_stage(client,'playback_retargeted');thread.join(2)
        deadline=time.monotonic()+2
        while not data2 and time.monotonic()<deadline:time.sleep(.02)
        assert data2 and not thread.is_alive()
        trace=(persistent_sdk/'trace').read_text().splitlines()
        assert trace.count('login')==trace.count('playback')==trace.count('seek')==1
        assert 'playback_stop' not in trace
    finally:
        if write>=0:os.close(write)
        if write2>=0:os.close(write2)
        if client:client.close()
        thread.join(3);thread2.join(3)
    assert not thread2.is_alive()

def test_decoded_frames_resume_after_seek_without_native_reopen(persistent_sdk):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    import artin_sentinel.playback_session_pool as module
    source=(persistent_sdk/'fake.cpp').read_text()+'''\nextern "C" int CLIENT_SeekPlayBackByTime(long h,NetTime* t){if(h!=0x23456789aL)std::_Exit(102);trace("seek");return 1;}\n'''
    (persistent_sdk/'fake.cpp').write_text(source)
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(persistent_sdk/'fake.cpp'),'-o',str(persistent_sdk/'libdhnetsdk.so')],check=True)
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=gray:s=160x90:r=20','-t','12','-c:v','mpeg2video','-f','mpegts',str(persistent_sdk/'media')],check=True)
    pool=PlaybackSessionPool();previous=module._pool;module._pool=pool
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00'
    session=IntelbrasCloudLiveSession(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=persistent_sdk,playback=True)
    try:
        session.start();deadline=time.monotonic()+5
        while not session.frame_count and time.monotonic()<deadline:time.sleep(.02)
        assert session.frame_count
        assert session.request_playback_seek(url.replace('08:00:00','08:20:00'),8) is True
        deadline=time.monotonic()+6
        while (session._seek_busy or session.playback_speed!=8) and time.monotonic()<deadline:time.sleep(.02)
        assert not session._seek_busy,session.drain_diagnostics()
        assert session.playback_speed==8 and session.current_state=='playing'
        trace=(persistent_sdk/'trace').read_text().splitlines()
        assert trace.count('playback')==trace.count('login')==trace.count('seek')==1
        for minute,speed in ((10,1),(30,16)):
            assert session.request_playback_seek(url.replace('08:00:00',f'08:{minute}:00'),speed) is True
            deadline=time.monotonic()+6
            while session._seek_busy and time.monotonic()<deadline:time.sleep(.02)
            assert not session._seek_busy,session.drain_diagnostics()
            assert session.playback_speed==speed
        trace=(persistent_sdk/'trace').read_text().splitlines()
        assert trace.count('seek')==3 and trace.count('playback')==trace.count('login')==1
    finally:
        session.stop();session.wait_closed(6);pool.shutdown();module._pool=previous

def test_ui_keeps_existing_session_for_silent_seek(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace as NS
    from artin_sentinel.app import MainWindow
    calls=[];start=datetime(2026,10,19,8);end=datetime(2026,10,19,9)
    session=NS(request_playback_seek=lambda url,speed:calls.append((url,speed)) or True)
    host=NS(playback_clip_bounds=(start,end),playback_seek=NS(value=lambda:120,setEnabled=lambda x:None),
        playback_multi_check=NS(isChecked=lambda:False),selected_playback_clip=lambda:('127.0.0.1',37777,1,start,end,('u','p')),
        selected_recording_row=lambda:None,recording_route=lambda *a:'native-route',playback_session=session,
        playback_listen_check=NS(isChecked=lambda:False),playback_speed_combo=NS(currentData=lambda:8),
        stop_playback_stream=lambda **kw:(_ for _ in ()).throw(AssertionError('session was reopened')))
    import artin_sentinel.playback_layout as layout
    monkeypatch.setattr(layout,'set_video_busy',lambda *a:None)
    MainWindow.seek_playback_stream(host)
    assert host.playback_session is session and host.playback_offset_seconds==120
    assert calls==[('native-route',8)]

def test_fast_decoder_discards_nonreference_frames_before_scaling():
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00'
    fast=IntelbrasCloudLiveSession(url,'u','p',playback=True,playback_speed=16)
    normal=IntelbrasCloudLiveSession(url,'u','p',playback=True)
    command=fast._command(url)
    assert command.index('-skip_frame')<command.index('-i')
    assert command[command.index('-skip_frame')+1]=='noref'
    assert '-skip_frame' not in normal._command(url)


def test_h264_hevc_fast_decode_produces_bounded_rgb_output(tmp_path):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    from artin_sentinel.live import FRAME_SIZE
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00'
    session=IntelbrasCloudLiveSession(url,'u','p',playback=True,playback_speed=16)
    for encoder in ('libx264','libx265'):
        payload=tmp_path/(encoder+'.ts')
        options=['-x265-params','pools=1:frame-threads=1:log-level=error'] if encoder=='libx265' else []
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=20','-t','4','-c:v',encoder,*options,'-g','20','-f','mpegts',str(payload)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        result=subprocess.run(session._command(url),input=payload.read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        assert result.returncode==0,result.stderr[-1000:]
        assert len(result.stdout)>=FRAME_SIZE and len(result.stdout)%FRAME_SIZE==0
        assert len(result.stdout)//FRAME_SIZE<12

def test_refused_seek_closes_worker_without_second_login(persistent_sdk,monkeypatch):
    from artin_sentinel.intelbras_cloud import BridgeProcess
    source=(persistent_sdk/'fake.cpp').read_text()+'''\nextern "C" int CLIENT_SeekPlayBackByTime(long h,NetTime* t){trace("seek_refused");return 0;}\n'''
    (persistent_sdk/'fake.cpp').write_text(source)
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(persistent_sdk/'fake.cpp'),'-o',str(persistent_sdk/'libdhnetsdk.so')],check=True)
    w,_,t=consume_pipe();w2,_,t2=consume_pipe();client=None
    try:
        client=BridgeProcess(55162,'TEST-SERIAL-PRIVATE','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=persistent_sdk,media_fd=w,playback_window={'start':'2026-10-19T08:00:00','end':'2026-10-19T09:00:00'},persistent=True)
        os.close(w);w=-1;wait_stage(client,'stream_data_received')
        client.retarget_playback(w2,at='2026-10-19T08:20:00',speed=1,ident=7)
        os.close(w2);w2=-1;wait_stage(client,'playback_retarget_failed')
        client.process.wait(timeout=4);client.poll_events()
        assert client.process.returncode!=0
    finally:
        for fd in (w,w2):
            if fd>=0:os.close(fd)
        if client:client.close()
        t.join(3);t2.join(3)
    trace=(persistent_sdk/'trace').read_text().splitlines()
    assert trace.count('login')==trace.count('playback')==trace.count('logout')==trace.count('cleanup')==1
    assert not t.is_alive() and not t2.is_alive()

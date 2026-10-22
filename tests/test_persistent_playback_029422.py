"""Offline: the synthetic NetSDK uses callbacks and pipes, never sockets."""
import os
import subprocess
import threading
import time
from pathlib import Path
import pytest

@pytest.fixture
def persistent_sdk(tmp_path, monkeypatch):
    source = (Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp').read_text()
    source = source.replace('trace("playback");sender=', 'stopped=false;paused=false;char stamp[32];std::snprintf(stamp,sizeof(stamp),"minute=%u",begin->minute);trace(stamp);trace("playback");sender=')
    source = source.replace('return CLIENT_StopRealPlayEx(handle);','int ok=CLIENT_StopRealPlayEx(handle);return scenario("stop_failed") ? 0 : ok;')
    (tmp_path/'fake.cpp').write_text(source)
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(tmp_path/'fake.cpp'),'-o',str(tmp_path/'libdhnetsdk.so')],check=True)
    payload=tmp_path/'media';payload.write_bytes(b'x'*188)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    monkeypatch.setenv('FAKE_TRACE',str(tmp_path/'trace'))
    return tmp_path

def consume_pipe():
    read,write=os.pipe();data=[]
    def consume():
        try:
            while chunk:=os.read(read,65536):data.append(chunk)
        finally:os.close(read)
    thread=threading.Thread(target=consume);thread.start()
    return write,data,thread

def wait_stage(client,stage,timeout=4):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        client.poll_events()
        if any(e['stage']==stage for e in client.events):return
        if client.process.poll() is not None:break
        time.sleep(.02)
    pytest.fail(f'Expected {stage}: {client.events}')

def test_same_login_is_kept_for_new_time_and_speed(persistent_sdk):
    from artin_sentinel.intelbras_cloud import BridgeProcess
    write,data,thread=consume_pipe()
    window={'start':'2026-10-19T08:00:00','end':'2026-10-19T09:00:00'}
    client=None
    try:
        client=BridgeProcess(55162,'TEST-SERIAL-PRIVATE','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=persistent_sdk,media_fd=write,playback_window=window,persistent=True)
        os.close(write);write=-1
        wait_stage(client,'stream_data_received');pid=client.process.pid
        client.request_stop();assert client.wait_idle(4)
        thread.join(2);assert data and not thread.is_alive()
        assert 'logout' not in (persistent_sdk/'trace').read_text().splitlines()
        write,data,thread=consume_pipe()
        client.resume_playback(write,channel=1,stream='main',playback_window=dict(window,start='2026-10-19T08:20:00'),playback_speed=4)
        os.close(write);write=-1
        wait_stage(client,'stream_data_received')
        assert client.process.pid==pid
        client.request_stop();assert client.wait_idle(4)
    finally:
        if write>=0:os.close(write)
        if client:client.close()
        thread.join(3)
    trace=(persistent_sdk/'trace').read_text().splitlines()
    assert trace.count('login')==1 and trace.count('playback')==2
    assert trace.count('logout')==1 and trace.count('cleanup')==1
    assert 'speed=2' in trace
    assert 'minute=20' in trace

def test_video_sessions_reuse_login_and_shutdown_cleans_it(persistent_sdk):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    import artin_sentinel.playback_session_pool as module
    pool=PlaybackSessionPool(idle_seconds=10)
    previous=module._pool;module._pool=pool
    payload=persistent_sdk/'media'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=gray:s=160x90:r=10','-f','lavfi','-i','sine=frequency=500:sample_rate=16000','-t','12','-c:v','mpeg2video','-c:a','mp2','-f','mpegts',str(payload)],check=True)
    sessions=[];audios=[]
    try:
        for minute,speed in ((0,1),(20,1),(30,4)):
            url=f'intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:{minute:02d}:00&end=2026-10-19T09:00:00'
            session=IntelbrasCloudLiveSession(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=persistent_sdk,playback=True,playback_speed=speed)
            sessions.append(session)
            audio=None
            if speed==1:
                audio=session.create_recording_audio(volume=40);audios.append(audio)
                audio._commands=lambda *a:[('test/null',['ffmpeg','-nostdin','-v','error','-probesize','1048576','-analyzeduration','1000000','-i','pipe:0','-map','0:a:0','-vn','-f','null','-','-progress','pipe:2','-stats_period','0.1'])]
                audio.start()
            session.start();deadline=time.monotonic()+5
            while not session.frame_count and time.monotonic()<deadline:time.sleep(.02)
            assert session.frame_count>0,session.drain_diagnostics()
            if audio:
                deadline=time.monotonic()+5
                while not audio._had_audio and time.monotonic()<deadline:time.sleep(.02)
                assert audio._had_audio
                audio.stop();assert audio.wait_closed(3)
            session.stop();assert session.wait_closed(6)
        trace=(persistent_sdk/'trace').read_text().splitlines()
        assert trace.count('login')==1 and trace.count('playback')==3
        assert trace.count('logout')==0
    finally:
        for audio in audios:audio.stop();audio.wait_closed(3)
        for session in sessions:session.stop();session.wait_closed(6)
        pool.shutdown();module._pool=previous
    assert (persistent_sdk/'trace').read_text().splitlines().count('logout')==1

def acquire_pipe(pool,sdk,speed=1,cancel=None):
    write,data,thread=consume_pipe()
    try:
        client=pool.acquire(55162,'TEST-SERIAL-PRIVATE','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',cancel_event=cancel or threading.Event(),sdk_dir=sdk,media_fd=write,channel=1,stream='main',playback_window={'start':'2026-10-19T08:00:00','end':'2026-10-19T09:00:00'},playback_speed=speed)
        return client,data,thread
    finally:os.close(write)

def test_released_owner_cannot_stop_next_playback_and_idle_expires(persistent_sdk):
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    pool=PlaybackSessionPool(idle_seconds=.2)
    threads=[]
    try:
        first,_,t=acquire_pipe(pool,persistent_sdk);threads.append(t)
        wait_stage(first,'stream_data_received');first.close()
        second,_,t=acquire_pipe(pool,persistent_sdk);threads.append(t)
        first.request_stop();wait_stage(second,'stream_data_received')
        assert second.client.cancel_fd>=0
        second.close()
        deadline=time.monotonic()+3
        while second.process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
        assert second.process.poll()==0
        assert (persistent_sdk/'trace').read_text().splitlines().count('logout')==1
    finally:
        pool.shutdown()
        for t in threads:t.join(3)

def test_waiting_cancel_does_not_create_another_login(persistent_sdk):
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    pool=PlaybackSessionPool();threads=[]
    try:
        first,_,t=acquire_pipe(pool,persistent_sdk);threads.append(t)
        wait_stage(first,'stream_data_received')
        cancel=threading.Event();timer=threading.Timer(.1,cancel.set);timer.start()
        with pytest.raises(ValueError,match='cancelada'):acquire_pipe(pool,persistent_sdk,cancel=cancel)
        timer.join(1)
        assert (persistent_sdk/'trace').read_text().splitlines().count('login')==1
        first.close()
    finally:
        pool.shutdown()
        for t in threads:t.join(3)

def test_unconfirmed_stop_is_not_cached(persistent_sdk,monkeypatch):
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    monkeypatch.setenv('FAKE_SCENARIO','stop_failed')
    pool=PlaybackSessionPool();client=None;thread=None
    try:
        client,_,thread=acquire_pipe(pool,persistent_sdk)
        wait_stage(client,'stream_data_received');client.close()
        assert not pool.entries and client.process.poll() is not None
        assert any(e['stage']=='stream_stop_failed' for e in client.events)
    finally:
        pool.shutdown()
        if thread:thread.join(3)

def test_failed_login_is_attempted_once_and_not_retained(persistent_sdk,monkeypatch):
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    monkeypatch.setenv('FAKE_SCENARIO','password')
    pool=PlaybackSessionPool();thread=None
    try:
        client,_,thread=acquire_pipe(pool,persistent_sdk)
        wait_stage(client,'login_failed');client.close()
        assert not pool.entries
        assert client.process.returncode==5
        assert (persistent_sdk/'trace').read_text().splitlines().count('login')==1
    finally:
        pool.shutdown()
        if thread:thread.join(3)

def test_dead_idle_worker_reconnects_on_next_request(persistent_sdk):
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    pool=PlaybackSessionPool();threads=[]
    try:
        first,_,t=acquire_pipe(pool,persistent_sdk);threads.append(t)
        wait_stage(first,'stream_data_received');first.close()
        pid=first.process.pid;first.process.kill();first.process.wait(timeout=2)
        second,_,t=acquire_pipe(pool,persistent_sdk);threads.append(t)
        wait_stage(second,'stream_data_received')
        assert second.process.pid!=pid
        assert (persistent_sdk/'trace').read_text().splitlines().count('login')==2
        second.close()
    finally:
        pool.shutdown()
        for t in threads:t.join(3)

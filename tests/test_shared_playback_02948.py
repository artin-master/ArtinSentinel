import os,time,threading
from types import SimpleNamespace


def test_slow_audio_subscriber_does_not_block_or_stop_video():
    from artin_sentinel.shared_playback_audio import PlaybackFanout
    source_read,source_write=os.pipe();video_read,video_write=os.pipe()
    fan=PlaybackFanout();audio=fan.subscribe();fan.start(source_read,video_write)
    payload=b'x'*65536;received=[]
    def consume():
        while True:
            chunk=os.read(video_read,65536)
            if not chunk:break
            received.append(chunk)
    reader=threading.Thread(target=consume);reader.start()
    for _ in range(100):os.write(source_write,payload)
    os.close(source_write);reader.join(3);fan.close();os.close(video_read)
    assert not reader.is_alive() and sum(map(len,received))==len(payload)*100
    assert fan.audio_overruns>0


def test_sdk_recording_audio_uses_the_video_session_without_new_sdk():
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    video=IntelbrasCloudLiveSession('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00','u','p',playback=True)
    audio=video.create_recording_audio(volume=40)
    assert audio.source is video and audio.volume==40
    assert audio.fanout is video._playback_fanout


def test_recording_video_continues_when_audio_starts_and_stops(tmp_path,monkeypatch):
    import subprocess
    from pathlib import Path
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    sdk=tmp_path/'sdk';sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    payload=tmp_path/'av.ts';trace=tmp_path/'trace'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=10','-f','lavfi','-i','sine=frequency=500:sample_rate=16000','-t','8','-c:v','mpeg2video','-c:a','mp2','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload));monkeypatch.setenv('FAKE_TRACE',str(trace))
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00'
    video=IntelbrasCloudLiveSession(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=sdk,playback=True)
    video.start();audio=None
    try:
        deadline=time.monotonic()+5
        while not video.frame_count and time.monotonic()<deadline:time.sleep(.02)
        assert video.frame_count>0,video.drain_diagnostics()
        before=video.frame_count;audio=video.create_recording_audio(volume=40)
        monkeypatch.setattr(audio,'_commands',lambda *a:[('test/null',['ffmpeg','-nostdin','-v','error','-probesize','1048576','-analyzeduration','1000000','-i','pipe:0','-map','0:a:0','-vn','-f','null','-','-progress','pipe:2','-stats_period','0.1'])])
        audio.start();deadline=time.monotonic()+5
        while not audio._had_audio and time.monotonic()<deadline:time.sleep(.02)
        assert audio._had_audio, (list(audio.status.queue),list(audio.diagnostics.queue),video.frame_count,video._playback_fanout.audio_overruns,video._playback_fanout.done.is_set(),video.drain_diagnostics())
        assert video.frame_count>before
        assert any('test/null' in line for line in audio.drain_diagnostics())
        audio.stop();assert audio.wait_closed(3)
        before=video.frame_count;time.sleep(.6)
        assert video.frame_count>before and video._thread.is_alive()
    finally:
        if audio:audio.stop();audio.wait_closed(3)
        video.stop();assert video.wait_closed(5)
    assert trace.read_text().splitlines().count('playback')==1
    assert trace.read_text().splitlines().count('login')==1


def test_audio_waits_for_video_transport_and_can_cancel(monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    video=IntelbrasCloudLiveSession('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00','u','p',playback=True)
    assert not video._playback_fanout.ready.is_set()
    audio=video.create_recording_audio();commands=[]
    monkeypatch.setattr(audio,'_commands',lambda *a:commands.append(1) or [])
    audio.start();time.sleep(.2)
    assert not commands
    audio.stop();assert audio.wait_closed(2)

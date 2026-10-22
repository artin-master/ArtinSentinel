from datetime import datetime
import time,subprocess
from pathlib import Path


def test_playback_small_packets_continue_beyond_initial_seconds(tmp_path,monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    sdk=tmp_path/'sdk';sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    payload=tmp_path/'video.ts';trace=tmp_path/'trace'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=10','-t','8','-c:v','mpeg2video','-q:v','2','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload));monkeypatch.setenv('FAKE_TRACE',str(trace));monkeypatch.setenv('FAKE_PLAYBACK_SMALL_CHUNKS','1')
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00'
    session=IntelbrasCloudLiveSession(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=sdk,playback=True)
    session.start();first=0
    try:
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            session.latest_frame();time.sleep(.02)
            if first==0 and session.frame_count: first=session.frame_count
        assert first>0
        assert session._thread.is_alive(),(session.frame_count,session.drain_diagnostics(),trace.read_text())
        before=session.frame_count;time.sleep(.5)
        assert session.frame_count>before,session.drain_diagnostics()
        assert 'pause' in trace.read_text() and 'resume' in trace.read_text(),trace.read_text()
    finally:session.stop();assert session.wait_closed(5)

from datetime import datetime
import pytest


def test_audio_subscribes_before_video_delivers_initial_header():
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    video = IntelbrasCloudLiveSession('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00', 'u', 'p', playback=True)
    audio = video.create_recording_audio()
    fan = video._playback_fanout
    assert fan.subscriber is not None, 'Audio must register before SDK emits the file header'
    stream = fan.subscriber
    audio.stop()
    assert fan.subscriber is None
    assert stream.get_nowait() is None


def test_export_bounds_keeps_marks_across_selected_files():
    from artin_sentinel.recording_export import export_bounds
    start, end = datetime(2026,10,19,14), datetime(2026,10,19,14,30)
    marked = datetime(2026,10,19,13)
    assert export_bounds(start, end, marked, end) == (marked, end)
    with pytest.raises(ValueError): export_bounds(start,end,end,start)


def test_cloud_export_uses_sdk_and_produces_audio_choice(tmp_path, monkeypatch):
    import subprocess, json
    from pathlib import Path
    from artin_sentinel.recording_export import export_mp4
    sdk = tmp_path/'sdk'; sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    payload=tmp_path/'av.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=10','-f','lavfi','-i','sine=frequency=500:sample_rate=16000','-t','4','-c:v','mpeg2video','-c:a','mp2','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload)); monkeypatch.setenv('FAKE_TRACE',str(tmp_path/'trace'))
    import artin_sentinel.intelbras_cloud as cloud
    monkeypatch.setattr(cloud,'default_sdk_dir',lambda:sdk)
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:59:57&end=2026-10-19T09:00:00'
    for sound in (False,True):
        target=tmp_path/('sound.mp4' if sound else 'silent.mp4'); updates=[]
        assert export_mp4(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',str(target),3,include_audio=sound,progress=updates.append)==target
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]))
        assert any(s['codec_type']=='video' for s in probe['streams'])
        assert any(s['codec_type']=='audio' for s in probe['streams']) is sound
        assert float(probe['format']['duration'])>=2.5
        assert '100%' in updates[-1]
    assert not list(tmp_path.glob('.sentinel-export-*'))


def test_cloud_export_cancel_during_transfer_removes_temporary_file(tmp_path,monkeypatch):
    import subprocess, threading
    from pathlib import Path
    from artin_sentinel.recording_export import export_mp4, RecordingExportError
    import artin_sentinel.intelbras_cloud as cloud
    sdk=tmp_path/'sdk';sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    payload=tmp_path/'av.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=10','-t','4','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload));monkeypatch.setenv('FAKE_TRACE',str(tmp_path/'trace'))
    monkeypatch.setattr(cloud,'default_sdk_dir',lambda:sdk)
    cancel=threading.Event();target=tmp_path/'cancelled.mp4'
    def progress(message):
        if message.startswith('Recebendo'): cancel.set()
    with pytest.raises(RecordingExportError,match='cancelada'):
        export_mp4('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00',
                    'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',str(target),3600,cancel=cancel,progress=progress)
    assert not target.exists() and not list(tmp_path.glob('.sentinel-export-*'))
    assert 'cleanup' in (tmp_path/'trace').read_text()


def test_audio_registration_preserves_first_bytes_even_before_audio_thread_runs():
    import os
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    video=IntelbrasCloudLiveSession('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00','u','p',playback=True)
    audio=video.create_recording_audio();fan=video._playback_fanout
    source_read,source_write=os.pipe();target_read,target_write=os.pipe()
    try:
        fan.start(source_read,target_write)
        os.write(source_write,b'file-header-only-once')
        assert os.read(target_read,100)==b'file-header-only-once'
        assert audio._initial_stream.get(timeout=1)==b'file-header-only-once'
    finally:
        audio.stop();os.close(source_write);fan.close();os.close(target_read)


def test_enabling_audio_after_video_started_reopens_current_position():
    from types import SimpleNamespace as NS
    import threading
    from artin_sentinel.app import MainWindow
    ready=threading.Event();ready.set();calls=[]
    video=NS(_playback_fanout=NS(ready=ready))
    host=NS(stop_playback_audio=lambda:calls.append('stop-audio'),
            playback_listen_check=NS(isChecked=lambda:True),
            playback_audio_muted=NS(isChecked=lambda:False),
            playback_audio_volume=NS(value=lambda:100),
            playback_audio_route=('route',('u','p')),
            playback_multi_check=NS(isChecked=lambda:False),playback_session=video,
            seek_playback_stream=lambda:calls.append('reopen-current-position'))
    MainWindow.toggle_playback_audio(host)
    assert calls==['stop-audio','reopen-current-position']


def test_short_cloud_response_never_publishes_success(tmp_path,monkeypatch):
    from types import SimpleNamespace as NS
    import os,subprocess,threading
    import artin_sentinel.intelbras_cloud as cloud
    from artin_sentinel.recording_export import export_mp4,RecordingExportError
    payload=tmp_path/'short.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=10','-t','1','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    class FiniteBridge:
        def __init__(self,*args,media_fd,**kwargs):
            self.stopped=False
            self.process=NS(poll=lambda:0 if self.stopped else None)
            fd=os.dup(media_fd)
            def send():
                try:
                    data=memoryview(payload.read_bytes())
                    while data:data=data[os.write(fd,data):]
                finally:os.close(fd)
            self.thread=threading.Thread(target=send);self.thread.start()
        def poll_events(self):return []
        def request_stop(self):self.stopped=True
        def close(self):self.thread.join(2)
    monkeypatch.setattr(cloud,'BridgeProcess',FiniteBridge)
    target=tmp_path/'incomplete.mp4'
    with pytest.raises(RecordingExportError,match='todo o intervalo'):
        export_mp4('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T08:00:10','u','p',str(target),10)
    assert not target.exists() and not list(tmp_path.glob('.sentinel-export-*'))

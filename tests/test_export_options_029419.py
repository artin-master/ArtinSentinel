import json,subprocess
from pathlib import Path
import pytest

@pytest.fixture
def export_source(tmp_path,monkeypatch):
    import artin_sentinel.intelbras_cloud as cloud
    sdk=tmp_path/'sdk';sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    payload=tmp_path/'original.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=1600x900:r=25','-f','lavfi','-i','sine=frequency=500:sample_rate=16000','-t','6','-c:v','libx264','-preset','ultrafast','-b:v','4000k','-c:a','aac','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload));monkeypatch.setenv('FAKE_TRACE',str(tmp_path/'trace'))
    monkeypatch.setenv('FAKE_PLAYBACK_SMALL_CHUNKS','1')
    monkeypatch.setenv('FAKE_PLAYBACK_PACKET_DELAY_US','500')
    monkeypatch.setattr(cloud,'default_sdk_dir',lambda:sdk)
    return payload

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))

@pytest.mark.parametrize('sound',[False,True])
def test_compact_exports_smaller_h264_with_independent_audio(export_source,tmp_path,sound):
    from artin_sentinel.recording_export import export_mp4
    url='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:59:55&end=2026-10-19T09:00:00'
    target=tmp_path/('compact-sound.mp4' if sound else 'compact-silent.mp4')
    export_mp4(url,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',str(target),5,quality='compact',include_audio=sound,diagnostics=print)
    info=probe(target);video=next(s for s in info['streams'] if s['codec_type']=='video')
    assert video['codec_name']=='h264' and (video['width'],video['height'])==(1280,720)
    a,b=video['avg_frame_rate'].split('/');assert float(a)/float(b)<=15.1
    assert any(s['codec_type']=='audio' for s in info['streams']) is sound
    assert target.stat().st_size<export_source.stat().st_size*.65
    assert float(info['format']['duration'])>=4.75
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(target),'-f','null','-'],check=True)

def test_compact_does_not_upscale_or_increase_low_fps(tmp_path):
    from artin_sentinel.recording_export_profiles import video_args
    out=tmp_path/'small.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=8','-t','2',*video_args('compact'),str(out)],check=True)
    video=next(s for s in probe(out)['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'])==(320,180)
    assert video['avg_frame_rate']=='8/1'

def test_unknown_quality_rejected_without_file_or_connection(tmp_path):
    from artin_sentinel.recording_export import export_mp4
    with pytest.raises(ValueError):
        export_mp4('rtsp://192.0.2.1/playback','u','p',str(tmp_path/'bad.mp4'),5,quality='bogus')
    assert not list(tmp_path.iterdir())

_APP=None

def test_options_default_original_audio_independent_and_estimate_before_save(monkeypatch):
    global _APP
    from datetime import datetime
    from PySide6.QtWidgets import QApplication,QMainWindow,QStackedWidget,QFileDialog
    from artin_sentinel.app import MainWindow
    import shiboken6
    _APP=QApplication.instance() or QApplication([])
    window=MainWindow.__new__(MainWindow);QMainWindow.__init__(window)
    window.pages=QStackedWidget();window.setCentralWidget(window.pages)
    window.playback_session=None;window.playback_audio_session=None;window.playback_sessions={};window.playback_active_channels=[]
    MainWindow.build_playback_page(window)
    window.playback_poll_timer.stop();window.playback_day_search_timer.stop()
    try:
        assert window.playback_export_quality.currentData()=='original'
        assert not window.playback_export_silent.isChecked()
        window.playback_export_quality.setCurrentIndex(1)
        window.playback_export_silent.setChecked(True)
        assert not window.playback_listen_check.isChecked()
        window.playback_export_worker=None;window.playback_trim_start=None;window.playback_trim_end=None
        window.selected_playback_clip=lambda:('route',55162,1,datetime(2026,10,20,13),datetime(2026,10,20,13,5),('u','p'))
        window.recording_route=lambda *a,**k:'unused'
        calls=[]
        monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(calls.append(a) or ('','')))
        MainWindow.export_selected_recording(window)
        assert 'Compacto' in calls[0][1] and 'estimativa' in calls[0][1]
        assert calls[0][2].endswith('_compacto_sem_audio.mp4')
    finally:shiboken6.delete(window)

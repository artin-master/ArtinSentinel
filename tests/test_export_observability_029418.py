from pathlib import Path
import json,os,select,subprocess,time
import pytest

_APP=None

URL='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:59:57&end=2026-10-19T09:00:00'

@pytest.fixture
def native_export(tmp_path,monkeypatch):
    import artin_sentinel.intelbras_cloud as cloud
    sdk=tmp_path/'sdk';sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    payload=tmp_path/'av.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=128x72:r=10','-f','lavfi','-i','sine=frequency=500:sample_rate=8000','-t','4','-c:v','libx265','-x265-params','pools=1:frame-threads=1:log-level=error','-c:a','pcm_mulaw',str(payload)],check=True,stderr=subprocess.DEVNULL)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload));monkeypatch.setenv('FAKE_TRACE',str(tmp_path/'trace'))
    monkeypatch.setattr(cloud,'default_sdk_dir',lambda:sdk)
    return sdk,payload


def test_hevc_and_mulaw_export_preserves_video_codec(native_export,tmp_path):
    from artin_sentinel.recording_export import export_mp4
    out=tmp_path/'hevc.mp4'
    export_mp4(URL,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',str(out),3)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out)]))
    assert next(s['codec_name'] for s in probe['streams'] if s['codec_type']=='video')=='hevc'
    assert next(s['codec_name'] for s in probe['streams'] if s['codec_type']=='audio')=='aac'
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(out),'-map','0:v:0','-map','0:a:0','-f','null','-'],check=True)


def test_native_export_reports_received_and_written_counts(native_export):
    from artin_sentinel.intelbras_cloud import BridgeProcess
    sdk,_=native_export
    read,write=os.pipe();client=None;events=[]
    try:
        client=BridgeProcess(55162,'TEST-SERIAL-PRIVATE','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',sdk_dir=sdk,media_fd=write,
                             playback_window={'start':'2026-10-19T08:59:57','end':'2026-10-19T09:00:00'},report_progress=True)
        os.close(write);write=-1
        until=time.monotonic()+4
        while time.monotonic()<until:
            if select.select([read],[],[],.1)[0]:os.read(read,65536)
            events.extend(client.poll_events())
            if any(e['stage']=='stream_progress' and e['written']>0 for e in events):break
        progress=[e for e in events if e['stage']=='stream_progress']
        assert progress and progress[-1]['bytes']>=progress[-1]['written']>0
    finally:
        if client:client.request_stop()
        os.close(read)
        if write>=0:os.close(write)
        if client:client.close()


def test_export_failure_has_diagnostic_stage_without_credentials(native_export,tmp_path,monkeypatch):
    from artin_sentinel.recording_export import export_mp4,RecordingExportError
    monkeypatch.setenv('FAKE_SCENARIO','password');messages=[]
    with pytest.raises(RecordingExportError):
        export_mp4(URL,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',str(tmp_path/'denied.mp4'),3,diagnostics=messages.append)
    text='\n'.join(messages)
    assert 'login_failed' in text
    assert all(secret not in text for secret in ['TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE','TEST-SERIAL-PRIVATE'])
    assert not list(tmp_path.glob('.sentinel-export-*'))


def test_progress_bar_shows_actual_percentage_instead_of_busy_animation():
    from types import SimpleNamespace as NS
    from PySide6.QtWidgets import QApplication,QProgressDialog
    from artin_sentinel.app import MainWindow
    global _APP
    _APP=QApplication.instance() or QApplication([])
    app=_APP
    dialog=QProgressDialog('Preparando','Cancelar',0,0)
    host=NS(playback_export_dialog=dialog)
    MainWindow.playback_export_progress(host,'Exportando gravação • 16% • 50s decorridos')
    assert (dialog.minimum(),dialog.maximum(),dialog.value())==(0,100,16)
    MainWindow.playback_export_progress(host,'Validando duração e conteúdo do MP4…')
    assert dialog.value()==16
    MainWindow.playback_export_progress(host,'Concluído • 100%')
    assert dialog.value()==99  # Owner closes only after final publication and cleanup.
    dialog.close();dialog.deleteLater();app.processEvents()

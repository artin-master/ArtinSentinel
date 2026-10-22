import json
from datetime import datetime
import pytest
import os
from pathlib import Path
import select
import subprocess
import shutil
import time

_APP=None

@pytest.fixture
def sdk_library(tmp_path,monkeypatch):
    import artin_sentinel.hik_sdk as module
    header=Path(os.environ.get('HIK_HEADER_DIR','/nonexistent'))/'HCNetSDK.h'
    if not header.is_file():pytest.skip('Set HIK_HEADER_DIR to test native IPC against the official header')
    subprocess.run(['g++','-shared','-fPIC','-I',str(header.parent),str(Path(__file__).with_name('fake_hik_sdk.cpp')),'-o',str(tmp_path/'libhcnetsdk.so')],check=True)
    monkeypatch.setattr(module,'runtime_dir',lambda:tmp_path)
    return tmp_path

def test_sdk_routes_are_opt_in_and_channels_are_explicit():
    from artin_sentinel.hik_sdk import live_choice
    device={'ip':'192.0.2.1','provider':'hikvision','metadata_json':'{}'}
    assert live_choice(device,1) is None
    device['metadata_json']=json.dumps({'hik_sdk':{'enabled':True,'live':True,'port':8000,'channels':{'1':1,'17':33}}})
    assert live_choice(device,1)[1].startswith('hik-sdk://192.0.2.1:8000/1?')
    assert '/33?' in live_choice(device,17)[1]
    assert live_choice(device,18) is None

def test_saved_sub_preference_is_preserved_in_both_windows():
    from types import SimpleNamespace
    from artin_sentinel.app import MainWindow,DetachedMonitorWindow
    device={'ip':'192.0.2.1','metadata_json':json.dumps({'hik_sdk':{'enabled':True,'live':True,'channels':{'1':1}}})}
    host=SimpleNamespace(db=SimpleNamespace(get_device=lambda _id:device))
    channel={'device_id':1,'channel_no':1,'preferred_stream':'sub'}
    for cls in (MainWindow,DetachedMonitorWindow):
        choice=cls._stream_choice(host,channel)
        assert choice[0]=='sub' and 'stream=sub' in choice[1]

def test_route_parser_rejects_credentials_cloud_and_invalid_period():
    from artin_sentinel.hik_sdk import parse_route,route
    for bad in ['hik-sdk://user:secret@192.0.2.1:8000/1?stream=main','hik-sdk://cloud:8000/1?stream=main',
                'hik-sdk://192.0.2.1:8000/1?stream=main&unexpected=x']:
        with pytest.raises(ValueError):parse_route(bad)
    url=route('192.0.2.1',8000,1,datetime(2026,10,21,21,20),datetime(2026,10,21,21,25))
    assert parse_route(url)['channel']==1

def test_plain_hikvision_search_route_is_unchanged():
    from artin_sentinel.hik_sdk import settings
    assert not settings({'metadata_json':'{}'})['enabled']

def test_sdk_uses_existing_xdg_data_location(tmp_path,monkeypatch):
    from artin_sentinel.hik_sdk import data_dir
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path))
    assert data_dir()==tmp_path/'artin-sentinel'

def test_runtime_import_is_persistent(sdk_library,tmp_path,monkeypatch):
    import artin_sentinel.hik_sdk as sdk
    source=tmp_path/'source';source.mkdir()
    shutil.copy2(sdk_library/'libhcnetsdk.so',source/'libhcnetsdk.so')
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'data'))
    imported=Path(sdk.import_runtime(source))
    assert (imported/'libhcnetsdk.so').is_file()
    config=json.loads((sdk.data_dir()/'hik-sdk-runtime.json').read_text())
    assert config['library_dir']==str(imported)
    shutil.rmtree(source)
    assert (imported/'libhcnetsdk.so').is_file()

def test_cancelled_query_does_not_create_login_process(monkeypatch):
    from threading import Event
    import artin_sentinel.hik_sdk as sdk
    cancel=Event();cancel.set()
    monkeypatch.setattr(sdk,'Client',lambda *a,**k:pytest.fail('cancelled search must not login'))
    from artin_sentinel.recording_search import RecordingSearchError
    with pytest.raises(RecordingSearchError,match='cancelada'):
        sdk.search_recordings({},'user','secret',(1,),datetime(2026,10,21),datetime(2026,10,22),cancel_event=cancel)

def test_import_rejects_symlink_outside_source(tmp_path,monkeypatch):
    from artin_sentinel.hik_sdk import import_runtime
    root=tmp_path/'sdk';root.mkdir()
    (root/'libhcnetsdk.so').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):import_runtime(root)

def test_native_search_and_session_cleanup(sdk_library):
    from artin_sentinel.hik_sdk import search_recordings
    device={'ip':'192.0.2.1','metadata_json':json.dumps({'hik_sdk':{'enabled':True,'channels':{'1':1}}})}
    result=search_recordings(device,'admin','secret-test',(1,),datetime(2026,10,21),datetime(2026,10,22))
    assert len(result.recordings)==1
    assert result.recordings[0].playback_uri.startswith('hik-sdk:')
    assert 'secret-test' not in str(result) and 'private-name' not in str(result)

@pytest.mark.parametrize('playback',[False,True])
def test_native_media_ipc_cancel_and_cleanup(sdk_library,playback):
    from artin_sentinel.hik_sdk import Client
    read,write=os.pipe()
    options=dict(host='192.0.2.1',port=8000,channel=1,stream='main')
    if playback:options.update(start='2026-10-21T21:20:00',end='2026-10-21T21:25:00')
    client=Client(options,'admin','secret-test',media_fd=write)
    os.close(write)
    try:
        assert select.select([read],[],[],5)[0]
        received=os.read(read,4096)
        assert received
    finally:
        client.close();os.close(read)
    assert client.process.poll()==0
    stages=[event['stage'] for event in client.events]
    assert stages.count('login_ok')==1
    assert 'stream_closed' in stages and 'logout' in stages and 'cleanup' in stages
    assert 'secret-test' not in json.dumps(client.events)

@pytest.mark.parametrize('playback',[False,True])
def test_sdk_media_reaches_existing_frame_queue(sdk_library,tmp_path,monkeypatch,playback):
    from artin_sentinel.hik_sdk_live import HikSDKLiveSession
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:pytest.skip('ffmpeg required')
    sample=tmp_path/'sample.mpg'
    subprocess.run([ffmpeg,'-loglevel','error','-f','lavfi','-i','testsrc=size=128x72:rate=10','-t','5',
        '-c:v','mpeg2video','-f','mpeg',str(sample)],check=True,timeout=10)
    monkeypatch.setenv('ARTIN_TEST_VIDEO',str(sample))
    from artin_sentinel.hik_sdk import route
    url=route('192.0.2.1',8000,1,datetime(2026,10,21,21,20) if playback else None,datetime(2026,10,21,21,25) if playback else None)
    session=HikSDKLiveSession(url,'admin','secret-test',fps=5,playback=playback)
    session.start();frame=None
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            frame=session.latest_frame()
            if frame is not None:break
            time.sleep(.05)
    finally:session.stop()
    assert frame is not None
    assert session.ever_had_frame

def test_login_failure_is_an_error_not_an_empty_day(sdk_library):
    from artin_sentinel.hik_sdk import search_recordings
    from artin_sentinel.recording_search import RecordingSearchError
    device={'ip':'192.0.2.1','metadata_json':json.dumps({'hik_sdk':{'enabled':True,'channels':{'1':1}}})}
    with pytest.raises(RecordingSearchError):
        search_recordings(device,'fail','secret',(1,),datetime(2026,10,21),datetime(2026,10,22))

def test_device_dialog_saves_sdk_opt_in_without_touching_routes(monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication,QWidget,QCheckBox,QDialogButtonBox
    from PySide6.QtCore import QTimer
    import artin_sentinel.hik_sdk_ui as ui
    global _APP
    _APP=app=QApplication.instance() or QApplication([])
    device={'ip':'192.0.2.1','kind':'dvr','manufacturer':'Hikvision','provider':'hikvision','metadata_json':'{}'}
    writes=[]
    window=QWidget()
    window.selected_device_id=lambda:1
    window.db=SimpleNamespace(get_device=lambda _id:device,merge_device_metadata=lambda did,patch:writes.append(patch))
    window.refresh_playback_access=lambda:None
    window.refresh_device_inspector=lambda:None
    monkeypatch.setattr(ui,'runtime_dir',lambda:Path('/fake/runtime'))
    monkeypatch.setattr(ui.QMessageBox,'information',lambda *a:None)
    def accept():
        dialog=app.activeModalWidget()
        assert dialog is not None
        for checkbox in dialog.findChildren(QCheckBox):checkbox.setChecked(True)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
    QTimer.singleShot(50,accept)
    ui.configure(window)
    assert writes==[{'hik_sdk':{'enabled':True,'live':True,'port':8000,'channels':{'1':1}}}]
    window.close()
    import shiboken6
    shiboken6.delete(window)

def test_finite_recording_drains_and_finishes_without_timeout(sdk_library,tmp_path,monkeypatch):
    from artin_sentinel.hik_sdk_live import HikSDKLiveSession
    from artin_sentinel.hik_sdk import route
    sample=tmp_path/'finite.mpg'
    subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','testsrc=size=128x72:rate=10','-t','5',
        '-c:v','mpeg2video','-f','mpeg',str(sample)],check=True,timeout=10)
    monkeypatch.setenv('ARTIN_TEST_VIDEO',str(sample));monkeypatch.setenv('ARTIN_TEST_COMPLETE','1')
    url=route('192.0.2.1',8000,1,datetime(2026,10,21,21,20),datetime(2026,10,21,21,25))
    session=HikSDKLiveSession(url,'admin','secret-test',fps=5,playback=True)
    session.start()
    try:
        assert session._finished.wait(15)
        assert session.current_state=='completed'
        assert session.frame_count>=20
        assert session._completed_source
        assert session.latest_status().startswith('Fim do trecho')
    finally:session.stop()

@pytest.mark.parametrize('quality',['original','compact'])
@pytest.mark.parametrize('include_audio',[False,True])
def test_sdk_export_creates_playable_mp4(sdk_library,tmp_path,monkeypatch,quality,include_audio):
    from artin_sentinel.recording_export import export_mp4
    from artin_sentinel.hik_sdk import route
    sample=tmp_path/'export.mpg'
    subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','testsrc=size=128x72:rate=10',
        '-f','lavfi','-i','sine=frequency=1000:sample_rate=48000','-t','3',
        '-c:v','mpeg2video','-c:a','mp2','-f','mpeg',str(sample)],check=True,timeout=10)
    monkeypatch.setenv('ARTIN_TEST_VIDEO',str(sample));monkeypatch.setenv('ARTIN_TEST_COMPLETE','1')
    url=route('192.0.2.1',8000,1,datetime(2026,10,21,21,20),datetime(2026,10,21,21,20,3))
    target=tmp_path/'saved.mp4'
    assert export_mp4(url,'admin','secret-test',str(target),3,quality=quality,include_audio=include_audio)==target
    info=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type','-of','json',str(target)],capture_output=True,text=True,check=True,timeout=10)
    result=json.loads(info.stdout)
    assert float(result['format']['duration'])>=2.5
    assert any(s['codec_type']=='audio' for s in result['streams']) is include_audio

import json
import time
import shutil
import subprocess
import pytest
from test_intelbras_cloud_bridge_pilot import sdk,SERIAL,USER,PASSWORD


def test_sub_inventory_and_upgrade_preserve_channel_identity(tmp_path):
    from artin_sentinel.db import Database
    from artin_sentinel.intelbras_cloud import register_bridge_inventory,parse_bridge_route,upgrade_cloud_inventory
    db=Database(tmp_path/'db')
    did=register_bridge_inventory(db,db.list_sites()[0]['id'],'Cloud',SERIAL,37777,4,managed=True)
    ch=db.list_recorder_channels(did)[0]
    assert ch['sub_rtsp_url'] and ch['sub_rtsp_url']!=ch['main_rtsp_url']
    assert parse_bridge_route(ch['sub_rtsp_url'])==(37777,SERIAL,1)
    db.update_channel_alias(ch['id'],'Portão')
    db.conn.execute("UPDATE recorder_channels SET sub_rtsp_url='',preferred_stream='sub' WHERE id=?",(ch['id'],))
    db.conn.execute("UPDATE devices SET canonical_type='unknown' WHERE id=?",(did,));db.conn.commit()
    upgrade_cloud_inventory(db)
    updated=db.get_recorder_channel(ch['id'])
    assert updated['sub_rtsp_url'] and updated['alias']=='Portão' and updated['preferred_stream']=='sub'
    assert db.get_device(did)['canonical_type']=='xvr'
    assert db.confirm_native_channel_frame(ch['id'],route=updated['sub_rtsp_url'])
    assert not db.confirm_native_channel_frame(ch['id'],route=updated['sub_rtsp_url'].replace('37777','37778'))


@pytest.mark.parametrize('stream,profile,type_number',[('main','Main stream',2),('sub','Substream',3)])
def test_live_selects_real_sdk_stream(sdk,tmp_path,monkeypatch,stream,profile,type_number):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession,bridge_route
    monkeypatch.setenv('FAKE_EXPECT_STREAM',str(type_number))
    payload=tmp_path/'media.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=160x90:r=10','-t','1','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    session=IntelbrasCloudLiveSession(bridge_route(55162,SERIAL,1,stream=stream),USER,PASSWORD,sdk_dir=sdk,profile_name=profile)
    try:
        session.start();frame=None;deadline=time.monotonic()+8
        while frame is None and time.monotonic()<deadline:frame=session.latest_frame();time.sleep(.02)
        assert frame is not None,session.drain_diagnostics()
        assert session.active_profile==profile
        assert 'primeiro quadro' in ' '.join(session.drain_diagnostics()).lower()
    finally:session.stop();assert session.wait_closed(5)


def test_default_mosaic_sub_and_explicit_main_follow_saved_routes(tmp_path):
    from artin_sentinel.db import Database
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    from artin_sentinel.app import MainWindow
    from types import SimpleNamespace
    db=Database(tmp_path/'db');did=register_bridge_inventory(db,db.list_sites()[0]['id'],'Cloud',SERIAL,37777,4,managed=True)
    ch=db.list_recorder_channels(did)[0]
    fake=SimpleNamespace(video_tiles=[1,2,3,4])
    assert MainWindow._stream_choice(fake,ch)[0:2]==('sub',ch['sub_rtsp_url'])
    assert MainWindow._stream_choice(fake,ch,'main')[0:2]==('main',ch['main_rtsp_url'])


def test_record_search_validates_identity_and_filters_returned_channel(sdk):
    from datetime import datetime
    from artin_sentinel.intelbras_cloud_recordings import search_cloud_recordings
    from artin_sentinel.recording_search import RecordingSearchError
    url='intelbras-cloud://127.0.0.1:55162/1?serial='+SERIAL
    result=search_cloud_recordings(url,USER,PASSWORD,[1],datetime(2026,10,19,8),datetime(2026,10,19,9),sdk_dir=sdk)
    assert len(result.recordings)==1
    record=result.recordings[0]
    assert record.channel==1 and record.start=='2026-10-19 08:10:00' and record.size==1024
    assert record.playback_uri.startswith('intelbras-cloud:')
    assert result.ignored==1
    with pytest.raises(RecordingSearchError):
        search_cloud_recordings(url.replace(SERIAL,'WRONG-SERIAL'),USER,PASSWORD,[1],datetime(2026,10,19,8),datetime(2026,10,19,9),sdk_dir=sdk)


def test_cloud_recorded_video_decodes_with_playback_api(sdk,tmp_path,monkeypatch):
    from datetime import datetime
    from artin_sentinel.intelbras_cloud_recordings import playback_route
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    payload=tmp_path/'recorded.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=10','-t','1','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    route=playback_route('intelbras-cloud://127.0.0.1:55162/1?serial='+SERIAL,datetime(2026,10,19,8),datetime(2026,10,19,9))
    session=IntelbrasCloudLiveSession(route,USER,PASSWORD,sdk_dir=sdk,profile_name='Gravação',playback=True)
    try:
        session.start();frame=None;deadline=time.monotonic()+8
        while frame is None and time.monotonic()<deadline:frame=session.latest_frame();time.sleep(.02)
        assert frame is not None,session.drain_diagnostics()
    finally:session.stop();assert session.wait_closed(5)
    assert 'playback' in (sdk/'trace').read_text().splitlines()
    assert 'playback_stop' in (sdk/'trace').read_text().splitlines()


def test_audio_decodes_stream_and_stops_without_orphans(sdk,tmp_path,monkeypatch):
    from artin_sentinel.intelbras_cloud_audio import IntelbrasCloudAudioSession
    payload=tmp_path/'audio.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:a','mp2','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    class NullOutput(IntelbrasCloudAudioSession):
        def _commands(self,*args):
            return [('Test/null',[shutil.which('ffmpeg'),'-v','error','-i','pipe:0','-map','0:a:0','-vn','-progress','pipe:2','-stats_period','0.1','-f','null','-'])]
    session=NullOutput('intelbras-cloud://127.0.0.1:55162/1?serial='+SERIAL,USER,PASSWORD,sdk_dir=sdk)
    try:
        session.start();deadline=time.monotonic()+8
        while not session._had_audio and not session.finished and time.monotonic()<deadline:time.sleep(.02)
        assert session._had_audio,session.drain_diagnostics()
    finally:session.stop();assert session.wait_closed(5)
    assert (sdk/'trace').read_text().splitlines()==['init','login','realplay','stop','logout','cleanup']


def test_saved_cloud_inventory_is_upgraded_when_database_reopens(tmp_path):
    from artin_sentinel.db import Database
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    path=tmp_path/'db';db=Database(path)
    did=register_bridge_inventory(db,db.list_sites()[0]['id'],'DVR',SERIAL,37777,4,managed=True)
    ch=db.list_recorder_channels(did)[0]
    db.conn.execute("UPDATE recorder_channels SET sub_rtsp_url='',preferred_stream='main',alias='Entrada' WHERE id=?",(ch['id'],))
    db.conn.commit();db.close()
    db=Database(path);row=db.get_recorder_channel(ch['id'])
    assert row['sub_rtsp_url'] and row['preferred_stream']=='main' and row['alias']=='Entrada'
    assert db.get_device(did)['model']==''


def test_audio_factory_preserves_local_sessions_and_routes_cloud():
    from artin_sentinel.live import create_live_audio_session,LiveAudioSession
    from artin_sentinel.intelbras_cloud_audio import IntelbrasCloudAudioSession
    assert type(create_live_audio_session('rtsp://192.0.2.1/live')) is LiveAudioSession
    assert isinstance(create_live_audio_session(['intelbras-wine://127.0.0.1:37777/1?serial='+SERIAL]),IntelbrasCloudAudioSession)


def test_ui_recording_route_preserves_cloud_time_and_serial():
    from datetime import datetime
    from artin_sentinel.app import MainWindow
    from artin_sentinel.recording_search import Recording
    from artin_sentinel.intelbras_cloud_recordings import playback_route
    begin,end=datetime(2026,10,19,8),datetime(2026,10,19,9)
    route=playback_route('intelbras-wine://127.0.0.1:37777/1?serial='+SERIAL,begin,end)
    record=Recording(1,str(begin),str(end),'Normal',1,route)
    result=MainWindow.recording_route(None,record,'',1,begin,end,37777)
    assert result==route


@pytest.mark.parametrize('extra',['&start=bad&end=bad','&start=2026-10-19T09:00:00&end=2026-10-19T08:00:00','&stream=other','&stream=sub&stream=main'])
def test_cloud_rejects_invalid_media_options(extra):
    from artin_sentinel.intelbras_cloud import parse_bridge_route
    with pytest.raises(ValueError):parse_bridge_route('intelbras-wine://127.0.0.1:37777/1?serial='+SERIAL+extra)


def test_audio_and_video_share_wine_and_stopping_audio_keeps_video(tmp_path,sdk,monkeypatch):
    import sys
    from artin_sentinel import intelbras_wine
    from artin_sentinel.intelbras_cloud_audio import IntelbrasCloudAudioSession
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    from test_intelbras_wine_manager import fake_process
    helper=fake_process(tmp_path)
    manager=intelbras_wine.WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',
        command_factory=lambda report,stop,port:[sys.executable,str(helper),str(report),str(stop),'ready','35551'])
    monkeypatch.setattr(intelbras_wine,'wine_manager',lambda:manager)
    monkeypatch.setenv('FAKE_EXPECT_PORT','35551')
    payload=tmp_path/'av.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=160x90:r=10','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','mpeg2video','-c:a','mp2','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    class NullOutput(IntelbrasCloudAudioSession):
        def _commands(self,*args):
            return [('Test/null',[shutil.which('ffmpeg'),'-v','error','-i','pipe:0','-map','0:a:0','-vn','-progress','pipe:2','-stats_period','0.1','-f','null','-'])]
    route='intelbras-wine://127.0.0.1:37777/1?serial='+SERIAL
    video=IntelbrasCloudLiveSession(route,USER,PASSWORD,sdk_dir=sdk)
    audio=NullOutput(route,USER,PASSWORD,sdk_dir=sdk)
    try:
        video.start();audio.start();frame=None;deadline=time.monotonic()+8
        while time.monotonic()<deadline and (frame is None or not audio._had_audio):
            frame=video.latest_frame() or frame;time.sleep(.02)
        assert frame is not None and audio._had_audio
        entry=next(iter(manager.entries.values()));assert entry.refs==2
        audio.stop();assert audio.wait_closed(5)
        assert entry.alive() and entry.refs==1
        assert video.frame_count>0
    finally:
        audio.stop();video.stop();audio.wait_closed(5);assert video.wait_closed(5);manager.shutdown()
    assert not manager.entries


def test_recording_does_not_restart_from_beginning_after_end(monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    class EndedRecording(IntelbrasCloudLiveSession):
        def _attempt_profile(self,*args):self.attempts+=1;return True
    session=EndedRecording('intelbras-cloud://127.0.0.1:55162/1?serial='+SERIAL,playback=True)
    monkeypatch.setattr(session._stop,'wait',lambda _:False)
    session._run()
    assert session.attempts==1 and session.reconnects==0

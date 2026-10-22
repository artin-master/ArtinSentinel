"""Native Main/Sub routing, pending-lens recovery and decoder regressions."""
import json
import shutil
import subprocess
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

from artin_sentinel import live, stream_diagnostics as diagnostics, xm_dvrip as native
from artin_sentinel.app import MainWindow, VideoTile
from artin_sentinel.db import Database
from artin_sentinel.domain import Device
from artin_sentinel.recorder import RecorderChannel
from artin_sentinel.direct_revalidation import recoverable_native_channel


def route(index=1, subtype=0):
    return f'dvrip://192.0.2.47:34567?channel={index}&subtype={subtype}'


@pytest.mark.parametrize('index,subtype', [(1,0),(1,1),(2,0),(2,1)])
def test_native_saved_routes_never_reach_rtsp_validator(monkeypatch,index,subtype):
    calls=[]
    def probe(host,user,password,**kw):
        calls.append((host,kw['channel'],kw['subtype'],kw['port']))
        return native.DvripMediaProbe(True,codec='hevc',detail='DVRIP vídeo recebido')
    monkeypatch.setattr(diagnostics,'probe_dvrip_media',probe)
    monkeypatch.setattr(diagnostics,'probe_rtsp_media_capabilities',lambda *a,**k:pytest.fail('DVRIP sent to RTSP'))
    monkeypatch.setattr(diagnostics,'ffmpeg_decoders',lambda:set())
    results=diagnostics.diagnose_saved_streams([{'channel_no':9,'main_rtsp_url':route(index,subtype),'sub_rtsp_url':route(index,subtype)}])
    assert calls==[('192.0.2.47',index,subtype,34567)]
    assert all(r.state=='native_validated' for r in results)
    assert all(r.native_index==index and r.subtype==subtype for r in results)
    assert 'Protocolo: DVRIP nativo' in results[0].summary()
    assert 'HEVC'.lower() in results[0].summary()
    assert 'Áudio: não verificado' in results[0].summary()
    assert 'RTSP inválida' not in results[0].summary()


def test_rtsp_still_uses_existing_probe(monkeypatch):
    probe=Mock(return_value=live.MediaProbeResult(ok=True,video_codec='h264'))
    monkeypatch.setattr(diagnostics,'probe_rtsp_media_capabilities',probe)
    monkeypatch.setattr(diagnostics,'probe_dvrip_media',lambda *a,**k:pytest.fail('RTSP sent to native'))
    diagnostics.diagnose_saved_streams([{'channel_no':1,'main_rtsp_url':'rtsp://camera/main','sub_rtsp_url':'rtsp://camera/sub'}])
    assert [c.args[0] for c in probe.call_args_list]==['rtsp://camera/main','rtsp://camera/sub']


@pytest.fixture
def fake_native(monkeypatch):
    packet=bytes((0,0,1,0xFC,0x03,12))+bytes(10)+b'video'
    class Session:
        def __init__(self,*a,**kw):
            self.sock=None; self.timeout=kw.get('timeout',1); self.closed=False
            self.kw=kw; self.calls=[]
            instances.append(self)
        def __enter__(self): return self
        def __exit__(self,*a): self.close()
        def close(self): self.closed=True
        def monitor_claim(self,*args): self.calls.append(('claim',*args))
        def monitor_start(self,*args): self.calls.append(('start',*args))
        def read_media_packet(self): return 0xFC,packet
    instances=[]
    monkeypatch.setattr(native,'DvripSession',Session)
    return Session,instances


def test_native_probe_reads_known_index_and_closes_session(fake_native):
    _,instances=fake_native
    result=native.probe_dvrip_media('192.0.2.47','admin','secret',channel=2,subtype=1,port=34568)
    assert result.ok and result.codec=='hevc' and result.fps==12
    assert instances[0].calls==[('claim',2,1),('start',2,1)]
    assert instances[0].kw['port']==34568 and instances[0].closed


@pytest.mark.parametrize('error,code',[
    (TimeoutError('secret'),'timeout'),
    (native.DvripError('credencial DVRIP recusada secret'),'authentication'),
    (native.DvripError('DVRIP não suportado secret'),'protocol_unsupported'),
    (native.DvripError('canal inexistente secret'),'stream_not_found'),
    (native.DvripError('claim recusado secret'),'media_unverified'),
])
def test_native_probe_errors_are_conservative_and_sanitized(fake_native,monkeypatch,error,code):
    cls,instances=fake_native
    def fail(self): raise error
    monkeypatch.setattr(cls,'read_media_packet',fail)
    result=native.probe_dvrip_media('192.0.2.47','admin','secret')
    assert not result.ok and result.error_code==code
    assert 'secret' not in result.detail and instances[0].closed


def test_cancel_native_probe_closes_session_and_discards_partial_diagnosis(fake_native,monkeypatch):
    cls,instances=fake_native
    cancel=Event()
    def cancel_read(self): cancel.set(); raise native.DvripError('interrupted')
    monkeypatch.setattr(cls,'read_media_packet',cancel_read)
    assert diagnostics.diagnose_saved_streams([{'channel_no':1,'rtsp_url':route()}],cancel_event=cancel)==[]
    assert instances[0].closed


def test_media_deadline_bounds_continuously_arriving_bytes():
    sock=Mock()
    sock.recv.return_value=b'x'
    with pytest.raises(TimeoutError):
        native._recv_exact(sock,100,deadline=0.00001)
    sock.recv.assert_not_called()


@pytest.fixture
def inventory(tmp_path):
    db=Database(tmp_path/'native.db')
    did=db.upsert_device(Device(site_id=db.list_sites()[0]['id'],name='IT-Blue',ip='192.0.2.47',provider='it-blue',kind='camera'))
    rows=[RecorderChannel(n,f'Lente {n}',route(n-1),True,200,'Rota direta • confirmada em campo',
        main_rtsp_url=route(n-1),sub_rtsp_url=route(n-1,1),route_kind='direct',channel_kind='ip') for n in (1,2,3)]
    db.replace_recorder_channels(did,rows)
    db.reconcile_direct_camera_channels(did,[],diagnostics=[{'position':n,'result':'unconfirmed'} for n in (1,2,3)])
    db.conn.execute('UPDATE recorder_channels SET available=0 WHERE device_id=?',(did,)); db.conn.commit()
    yield db,did
    db.close()


def test_pending_native_frame_promotes_only_matching_lens(inventory):
    db,did=inventory
    rows=db.list_recorder_channels(did)
    device=db.get_device(did)
    assert all(recoverable_native_channel(device,row) for row in rows)
    assert db.confirm_native_channel_frame(rows[1]['id'])
    after=db.list_recorder_channels(did)
    assert [r['available'] for r in after]==[0,1,0]
    assert [r['id'] for r in after]==[r['id'] for r in rows]
    assert [native.parse_dvrip_route(r['rtsp_url'])[2] for r in after]==[0,1,2]
    states=json.loads(db.get_device(did)['metadata_json'])['direct_channel_revalidation']
    assert states['2']['state']=='validated' and states['3']['state']=='temporarily_unavailable'


def test_retired_or_never_confirmed_native_route_cannot_bypass_gate(inventory):
    db,did=inventory
    row=dict(db.list_recorder_channels(did)[1]); device=dict(db.get_device(did))
    device['metadata_json']=json.dumps({'direct_channel_revalidation':{'2':{'state':'retired'}}})
    assert not recoverable_native_channel(device,row)
    device['metadata_json']='{}'; row['detail']='candidate'
    assert not recoverable_native_channel(device,row)


def test_pending_native_lens_opens_in_live_view_without_affecting_other_tile(inventory,monkeypatch):
    application=QApplication.instance() or QApplication([])
    db,did=inventory
    w=MainWindow.__new__(MainWindow); QMainWindow.__init__(w)
    w.db=db; w.video_tiles=[VideoTile(0),VideoTile(1)]; w.selected_video_tile=None; w.live_audio_tile_index=None
    other=Mock(); w.live_sessions={1:other}
    monkeypatch.setattr(w,'stop_tile_stream',Mock())
    monkeypatch.setattr(w,'_credentials_for_device',lambda _:('admin','secret'))
    monkeypatch.setattr(w,'_live_target_fps',lambda:10)
    session=Mock(); create=Mock(return_value=session)
    monkeypatch.setattr('artin_sentinel.app.create_live_stream_session',create)
    row=db.list_recorder_channels(did)[1]
    try:
        w.apply_source_to_tile(w.video_tiles[0],{'type':'channel','device_id':did,'channel_id':row['id'],'forced_stream':'sub'})
        assert create.call_args.args[0]==route(1,1)
        assert create.call_args.kwargs['stop_after_initial_failures']==3
        session.start.assert_called_once()
        assert w.live_sessions[1] is other and not other.mock_calls
    finally:
        for tile in w.video_tiles: tile.deleteLater()
        w.deleteLater(); application.processEvents()


def test_native_retry_remains_bounded_isolated_and_closed_channel_stays_closed(monkeypatch):
    a=live.create_live_stream_session(route(1),stop_after_initial_failures=3)
    b=live.create_live_stream_session(route(2),stop_after_initial_failures=3)
    attempts=[]
    monkeypatch.setattr(live.LiveStreamSession,'decoder_available',property(lambda _:True))
    monkeypatch.setattr(a,'_attempt_profile',lambda *args:attempts.append(args) or False)
    monkeypatch.setattr(a._stop,'wait',lambda _:False)
    a._run()
    assert len(attempts)==3 and a.current_state=='unavailable'
    assert b.attempts==0 and b.current_state=='idle'
    a.stop(); a._run()
    assert len(attempts)==3


@pytest.mark.parametrize("codec,encoder", [("h264","libx264"),("hevc","libx265")])
def test_native_decoder_keeps_initial_keyframe(codec,encoder):
    # Actual local FFmpeg regression: nobuffer discarded this valid short GOP.
    ffmpeg=shutil.which('ffmpeg')
    assert ffmpeg, 'FFmpeg required for local native decoder validation'
    encoded=subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10',
        '-frames:v','20','-c:v',encoder,'-preset','ultrafast','-tune','zerolatency',
        *(['-x265-params','pools=1:frame-threads=1:log-level=error'] if codec=='hevc' else []),
        '-f',codec,'pipe:1'],
        capture_output=True,timeout=10,check=True).stdout
    s=live.create_live_stream_session(route(1),fps=10)
    result=subprocess.run(s._dvrip_decoder_command(codec),input=encoded,capture_output=True,timeout=10)
    assert result.returncode==0 and len(result.stdout)>=live.FRAME_SIZE
    assert '-rtsp_transport' not in s._dvrip_decoder_command('h264')


def test_timeout_native_diagnosis_preserves_inventory_and_pending_state(inventory,monkeypatch):
    db,did=inventory
    before=db.list_recorder_channels(did)
    monkeypatch.setattr(diagnostics,'probe_dvrip_media',lambda *a,**k:native.DvripMediaProbe(False,error_code='timeout',detail='Tempo limite DVRIP'))
    result=diagnostics.diagnose_saved_streams([dict(before[1])])
    assert all(r.state=='timeout' and r.protocol=='DVRIP nativo' for r in result)
    assert db.list_recorder_channels(did)==before
    assert recoverable_native_channel(db.get_device(did),before[1])


def test_known_native_index_is_not_derived_from_display_position(inventory,monkeypatch):
    from artin_sentinel import ip_camera
    db,did=inventory
    # Native channel 7 was previously confirmed as displayed position 2.
    row=dict(db.list_recorder_channels(did)[1]); row['available']=1
    row.update(rtsp_url=route(7),main_rtsp_url=route(7),sub_rtsp_url=route(7,1))
    calls=[]
    def probe(*a,**kw):
        calls.append((kw['channel'],kw['subtype']))
        return native.DvripMediaProbe(kw['channel']==7,codec='hevc',detail='DVRIP HEVC')
    monkeypatch.setattr(ip_camera,'probe_dvrip_media',probe)
    monkeypatch.setattr(ip_camera,'dvrip_multilens_hints',lambda *a,**k:{})
    monkeypatch.setattr(ip_camera,'validate_rtsp_media',lambda *a,**k:(False,'timeout'))
    monkeypatch.setattr(ip_camera.time,'sleep',lambda _:None)
    rows=ip_camera._scan_itblue_x3_multilens_rtsp('192.0.2.47','admin','secret',previous_channels=[row])
    assert calls[:2]==[(7,0),(7,1)]
    assert len(rows)==1 and rows[0].channel==2 and rows[0].main_rtsp_url==route(7)


@pytest.mark.parametrize('url',[route(-1),route(1,2),'dvrip://admin:secret@192.0.2.47?channel=1&subtype=0'])
def test_native_route_cannot_silently_fall_back_to_other_lens(url):
    with pytest.raises(ValueError): native.parse_dvrip_route(url)


def test_native_pipeline_delivers_frame_and_releases_decoder(monkeypatch):
    encoded=subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10',
        '-frames:v','20','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-f','h264','pipe:1'],
        capture_output=True,timeout=10,check=True).stdout
    packet=bytes((0,0,1,0xFC,0x02,10))+bytes(10)+encoded
    class Session:
        def __init__(self,*a,**k): self.sock=None; self.closed=False; self.read=False; instances.append(self)
        def connect(self): pass
        def login(self): pass
        def monitor_claim(self,*a): pass
        def monitor_start(self,*a): pass
        def read_media_packet(self):
            if self.read: raise native.DvripError('fixture complete')
            self.read=True; return 0xFC,packet
        def close(self): self.closed=True
    instances=[]
    monkeypatch.setattr(live,'DvripSession',Session)
    s=live.create_live_stream_session(route(1),fps=10)
    def frame_received(frame):
        assert len(frame.pixels)==live.FRAME_SIZE
        s._stop.set()
    monkeypatch.setattr(s,'_push_frame',frame_received)
    assert s._attempt_profile(s.url,'Main stream')
    assert s.ever_had_frame and instances[0].closed
    assert s._process is None and s._dvrip_session is None


def test_native_live_process_without_frames_is_reaped(monkeypatch):
    import sys
    packet=bytes((0,0,1,0xFC,0x02,10))+bytes(10)+b'video'
    class Session:
        def __init__(self,*a,**k): self.sock=None; self.closed=False; self.read=False; instances.append(self)
        def connect(self): pass
        def login(self): pass
        def monitor_claim(self,*a): pass
        def monitor_start(self,*a): pass
        def read_media_packet(self):
            if self.read: raise native.DvripError('fixture complete')
            self.read=True; return 0xFC,packet
        def close(self): self.closed=True
    instances=[]; processes=[]
    original=live.subprocess.Popen
    def spawn(*a,**k):
        p=original(*a,**k); processes.append(p); return p
    monkeypatch.setattr(live,'DvripSession',Session)
    monkeypatch.setattr(live.subprocess,'Popen',spawn)
    monkeypatch.setattr(live,'FRAME_INACTIVITY_TIMEOUT',0.05)
    s=live.create_live_stream_session(route(1))
    monkeypatch.setattr(s,'_dvrip_decoder_command',lambda _:[sys.executable,'-c','import time; time.sleep(30)'])
    assert not s._attempt_profile(s.url,'Main stream')
    assert s.last_error_class=='frame_timeout'
    assert 'DVRIP/decoder' in s.last_reconnect_cause
    assert instances[0].closed and all(p.poll() is not None for p in processes)
    assert s._process is None


def test_login_failure_closes_native_socket(monkeypatch):
    sock=Mock()
    def connect(self): self.sock=sock
    def login(self): raise native.DvripError('credencial DVRIP recusada')
    monkeypatch.setattr(native.DvripSession,'connect',connect)
    monkeypatch.setattr(native.DvripSession,'login',login)
    result=native.probe_dvrip_media('192.0.2.47','admin','secret')
    assert result.error_code=='authentication'
    sock.close.assert_called_once()


def test_cancelled_partial_packet_keeps_received_bytes(monkeypatch):
    sock=Mock()
    sock.recv.side_effect=[b'a',TimeoutError(),b'b']
    import time
    assert native._recv_exact(sock,2,deadline=time.monotonic()+1,cancel_event=Event())==b'ab'


def test_native_live_frame_revalidates_even_with_saved_profile_marker(inventory,monkeypatch):
    application=QApplication.instance() or QApplication([])
    db,did=inventory
    w=MainWindow.__new__(MainWindow); QMainWindow.__init__(w)
    w.db=db; w.selected_video_tile=None; w.live_audio_session=None; w.talkback_session=None
    row=db.list_recorder_channels(did)[1]
    tile=VideoTile(0); w.video_tiles=[tile]
    tile.set_source('Lente fixa 1','','',{'type':'channel','device_id':did,'channel_id':row['id'],'_last_good_saved':'main'})
    session=live.create_live_stream_session(row['rtsp_url'],profile_name='Main stream')
    session._push_frame(live.FramePacket(bytes(live.FRAME_SIZE)))
    w.live_sessions={0:session}
    monkeypatch.setattr(w,'poll_camera_events',Mock())
    try:
        w.poll_live_streams()
        assert db.get_recorder_channel(row['id'])['available']==1
        assert json.loads(db.get_device(did)['metadata_json'])['direct_channel_revalidation']['2']['state']=='validated'
        assert session._inventory_frame_confirmed
        assert db.list_recorder_channels(did)[2]['available']==0
    finally:
        tile.deleteLater(); w.deleteLater(); application.processEvents()

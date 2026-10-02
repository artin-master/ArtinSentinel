"""Wire-level receive regressions and independent native monitor sessions."""
import json
import socket
import struct
import subprocess
import threading
import time
from unittest.mock import Mock

import pytest
from artin_sentinel import live, xm_dvrip as native


def packet(payload=b'video', marker=3):
    return bytes((0,0,1,0xFC,marker,12,160,90))+bytes(4)+struct.pack('<I',len(payload))+payload


@pytest.mark.parametrize('channel,subtype',[(0,0),(0,1),(1,0),(1,1),(2,0),(2,1)])
def test_monitor_requests_preserve_native_channel_and_subtype(monkeypatch,channel,subtype):
    sock=Mock()
    s=native.DvripSession('192.0.2.47','operator','secret',sock=sock,session=0x12345678)
    command=Mock(return_value={'Ret':100})
    # Dataclass slots: spy on the method at class level.
    monkeypatch.setattr(native.DvripSession,'_send_json',lambda self,msg,payload:command(msg,payload))
    s.monitor_claim(channel,subtype); s.monitor_start(channel,subtype)
    request=command.call_args.args[1]
    assert command.call_args.args[0]==1413
    assert request['OPMonitor']['Parameter']==dict(Channel=channel,CombinMode='NONE',StreamType='Extra1' if subtype else 'Main',TransMode='TCP')
    header=native._HEADER.unpack(sock.sendall.call_args.args[0][:20])
    start=json.loads(sock.sendall.call_args.args[0][20:].rstrip(b'\n\x00'))
    assert header[4]==1410
    assert start['OPMonitor']['Action']=='Start'
    assert start['OPMonitor']['Parameter']==request['OPMonitor']['Parameter']
    assert s.monitor_reply_code==100


@pytest.mark.parametrize('marker,codec',[(0x22,'h264'),(0x63,'hevc'),(0x53,'hevc')])
def test_dimension_bits_do_not_change_video_codec(marker,codec):
    name,fps,width,height=native.dvrip_video_metadata(packet(marker=marker))
    assert name==codec and fps==12 and width>0 and height>0


def test_interleaved_monitor_ack_preserves_fragmented_media(monkeypatch):
    frame=packet(payload=b'{compressed-fragment}')
    chunks=iter([(1412,frame[:16]),(1411,b'{"Ret":100,"SessionID":"SENSITIVE"}\n\x00'),(1412,frame[16:])])
    monkeypatch.setattr(native.DvripSession,'read_stream_chunk',lambda self:next(chunks))
    s=native.DvripSession('192.0.2.47','operator','secret')
    kind,data=s.read_media_packet()
    assert kind==0xFC and data==frame
    assert s.media_packets_received==1 and s.monitor_reply_code==100


def test_media_chunk_starting_brace_is_not_discarded_as_json(monkeypatch):
    # Starting mid-frame is legal; resync finds the following native keyframe.
    data=b'{compressed-tail}'+packet()
    chunks=iter([(1412,data)])
    monkeypatch.setattr(native.DvripSession,'read_stream_chunk',lambda self:next(chunks))
    s=native.DvripSession('192.0.2.47','operator','secret')
    assert s.read_media_packet()[1]==packet()


def test_monitor_rejection_is_recorded_without_exporting_payload(monkeypatch):
    monkeypatch.setattr(native.DvripSession,'read_stream_chunk',lambda self:(1411,b'{"Ret":102,"SessionID":"PRIVATE","PassWord":"secret"}'))
    s=native.DvripSession('192.0.2.47','operator','secret')
    with pytest.raises(native.DvripError) as error:
        s.read_media_packet()
    assert s.monitor_reply_code==102
    assert 'PRIVATE' not in str(error.value) and 'secret' not in str(error.value)


def test_socket_poll_timeout_preserves_partial_frame_until_deadline():
    sock=Mock(); sock.recv.side_effect=[b'a',socket.timeout(),b'b']
    assert native._recv_exact(sock,2,deadline=time.monotonic()+1)==b'ab'


@pytest.fixture
def encoded_video():
    return subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10',
        '-frames:v','20','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-f','h264','pipe:1'],
        capture_output=True,timeout=10,check=True).stdout


@pytest.mark.parametrize('failing_channel',[None,1])
def test_simultaneous_native_sessions_and_cleanup_are_independent(monkeypatch,encoded_video,failing_channel):
    barrier=threading.Barrier(3); instances=[]
    class Session:
        def __init__(self,*a,**k):
            self.sock=None; self.closed=False; self.read=False; self.calls=[]
            self.monitor_reply_code=100; self.login_reply_code=100
            instances.append(self)
        def connect(self): self.calls.append('connect')
        def login(self): self.calls.append('login')
        def monitor_claim(self,channel,subtype): self.channel=channel; self.calls.append(('claim',channel,subtype))
        def monitor_start(self,channel,subtype): self.calls.append(('start',channel,subtype))
        def read_media_packet(self):
            if self.read: raise native.DvripError('fixture end')
            self.read=True; barrier.wait(timeout=5)
            if self.channel==failing_channel: raise TimeoutError('fixture timeout')
            if self.channel==2: time.sleep(0.05)
            return 0xFC,packet(encoded_video,marker=2)
        def close(self): self.closed=True
    monkeypatch.setattr(live,'DvripSession',Session)
    sessions=[live.create_live_stream_session(f'dvrip://192.0.2.47?channel={n}&subtype=0','operator','secret') for n in (0,1,2)]
    result={}
    for s in sessions:
        monkeypatch.setattr(s,'_push_frame',lambda frame,s=s:s._stop.set())
    threads=[threading.Thread(target=lambda n=n:result.update({n:sessions[n]._attempt_profile(sessions[n].url,'Main stream')})) for n in (0,1,2)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    assert not any(t.is_alive() for t in threads)
    assert result=={n:n!=failing_channel for n in (0,1,2)}
    assert len({id(s) for s in instances})==3 and all(s.closed for s in instances)
    for n,s in enumerate(sessions):
        assert s._process is None and s._dvrip_session is None
        assert s.native_diagnostics['channel']==n and s.native_diagnostics['subtype']==0
        assert s.native_diagnostics['first_frame']==(n!=failing_channel)
        if n==2:
            assert s.native_diagnostics['first_frame_ms']>=50
        report=' '.join(s.drain_diagnostics())
        assert 'secret' not in report and 'SessionID' not in report
        assert 'DVRIP final' in report
        own=next(i for i in instances if i.channel==n)
        assert own.calls==['connect','login',('claim',n,0),('start',n,0)]


def test_native_connections_own_distinct_sockets(monkeypatch):
    sockets=[Mock() for _ in range(3)]
    create=Mock(side_effect=sockets)
    monkeypatch.setattr(native.socket,'create_connection',create)
    sessions=[native.DvripSession('192.0.2.47','operator','secret') for _ in range(3)]
    for s in sessions: s.connect()
    assert [s.sock for s in sessions]==sockets
    assert create.call_count==3
    sessions[1].close()
    sockets[1].close.assert_called_once()
    sockets[0].close.assert_not_called(); sockets[2].close.assert_not_called()
    for s in sessions: s.close()
    assert all(s.sock is None for s in sessions)


def test_wire_chunk_metrics_count_only_complete_payloads(monkeypatch):
    body=packet()
    header=native._HEADER.pack(255,0,0x12345678,4,1412,len(body))
    sock=Mock(); sock.recv.side_effect=[header,body]
    s=native.DvripSession('192.0.2.47','operator','secret',sock=sock)
    assert s.read_media_packet()[1]==body
    assert s.media_bytes_received==len(body)
    assert s.media_chunks_received==s.media_packets_received==1
    assert s.last_media_message==1412


def test_payload_without_decoded_frame_has_distinct_field_diagnostic(monkeypatch):
    import sys
    class Session:
        def __init__(self,*a,**k): self.sock=None; self.read=False; self.closed=False; instances.append(self)
        def connect(self): pass
        def login(self): pass
        def monitor_claim(self,*args): pass
        def monitor_start(self,*args): pass
        def read_media_packet(self):
            if self.read: raise native.DvripError('fixture complete')
            self.read=True; return 0xFC,packet()
        def close(self): self.closed=True
    instances=[]
    monkeypatch.setattr(live,'DvripSession',Session)
    s=live.create_live_stream_session('dvrip://192.0.2.47?channel=2&subtype=1','operator','secret')
    monkeypatch.setattr(s,'_dvrip_decoder_command',lambda _:[sys.executable,'-c','import sys; sys.stdin.buffer.read()'])
    assert not s._attempt_profile(s.url,'Substream')
    d=s.native_diagnostics
    assert d['channel']==2 and d['subtype']==1 and d['login']=='ok' and d['monitor_sent']
    assert d['codec']=='hevc' and d['bytes']>0 and d['packets']==1
    assert not d['first_frame'] and d['classification']=='payload_without_frame'
    assert instances[0].closed and s._process is None
    assert 'secret' not in ' '.join(s.drain_diagnostics())


@pytest.mark.parametrize('stage,code',[('login','authentication'),('claim','monitor_rejected')])
def test_field_diagnostics_identify_rejected_stage_and_ret(monkeypatch,stage,code):
    class Session:
        def __init__(self,*a,**k): self.closed=False; self.login_reply_code=None; self.monitor_reply_code=None; instances.append(self)
        def connect(self): pass
        def login(self):
            self.login_reply_code=203 if stage=='login' else 100
            if stage=='login': raise native.DvripError('credencial DVRIP recusada')
        def monitor_claim(self,*a):
            self.monitor_reply_code=102
            raise native.DvripError('monitor DVRIP recusado')
        def close(self): self.closed=True
    instances=[]
    monkeypatch.setattr(live,'DvripSession',Session)
    s=live.create_live_stream_session('dvrip://192.0.2.47?channel=1&subtype=0','operator','secret')
    assert not s._attempt_profile(s.url,'Main stream')
    assert s.native_diagnostics['stage']==stage and s.native_diagnostics['classification']==code
    assert s.native_diagnostics['login_ret']==(203 if stage=='login' else 100)
    assert not s.native_diagnostics['monitor_sent'] and instances[0].closed
    report=' '.join(s.drain_diagnostics())
    assert 'secret' not in report and 'SessionID' not in report


def test_socket_inactivity_does_not_end_keyframe_deadline_early(monkeypatch):
    now=[0.0]
    monkeypatch.setattr(native.time,'monotonic',lambda:now[0])
    sock=Mock()
    def recv(size):
        now[0]+=3
        if now[0]==3: raise socket.timeout()
        return b'x'
    sock.recv.side_effect=recv
    assert native._recv_exact(sock,1,deadline=7)==b'x'
    assert now[0]==6  # Arrived later than the old 2.5s socket timeout, before total deadline.

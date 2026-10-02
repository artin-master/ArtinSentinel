import json
import socket

import pytest

from artin_sentinel.dvrip_events import (
    EventSession, EventProtocolError, EventWorker, detection_summary, _HEADER,
)


@pytest.mark.parametrize('ret,expected', [(100, 'yes'), (102, 'no'), (502, 'no'), (605, 'no')])
def test_subscription_dialect(ret, expected):
    session = EventSession('192.0.2.1', 'admin', 'secret')
    commands = []
    session._send_json = lambda code, payload: commands.append((code, payload)) or {'Ret': ret}
    assert session.subscribe() == expected
    assert commands == [(1500, {'Name': '', 'SessionID': '0x00000000'})]


def test_refusal_and_command_allowlist():
    session = EventSession('192.0.2.1', 'admin', 'secret')
    session._send_json = lambda *args: {'Ret': 107}
    with pytest.raises(EventProtocolError, match='subscription_refused'):
        session.subscribe()
    for code in (1040, 1506, 1450):
        with pytest.raises(EventProtocolError, match='command_not_allowed'):
            session.send_only(code, {})


class Socket:
    def __init__(self, parts): self.parts = iter(parts)
    def settimeout(self, value): pass
    def recv(self, size):
        part = next(self.parts)
        if isinstance(part, Exception): raise part
        return part


def packet(body, message=1504, length=None):
    raw = json.dumps(body).encode()
    return _HEADER.pack(255, 0, 1, 0, message, len(raw) if length is None else length) + raw


def test_partial_packet_survives_timeout():
    raw = packet({'Name': 'AlarmInfo'})
    session = EventSession('192.0.2.1', '', '')
    session.sock = Socket([raw[:7], socket.timeout(), raw[7:]])
    with pytest.raises(socket.timeout): session.receive()
    assert session.receive() == (1504, 1, {'Name': 'AlarmInfo'})


@pytest.mark.parametrize('raw,error', [(packet({}, length=100000), 'invalid_packet'), (packet([]), 'invalid_payload'), (_HEADER.pack(255, 0, 1, 0, 1504, 1)+b'x', 'invalid_json')])
def test_malformed_bounded(raw, error):
    session = EventSession('192.0.2.1', '', '')
    session.sock = Socket([raw])
    with pytest.raises(EventProtocolError, match=error): session.receive()


def test_read_only_summary_drops_secrets_and_free_text():
    summary = detection_summary({'MotionDetect': [{'Enable': True, 'Level': 3, 'Password': 'secret', 'Schedule': ['secret'], 'EventHandler': {'BeepEnable': True, 'FlashEnable': False, 'UserName': 'admin'}}]})
    assert len(summary) == 4
    assert 'secret' not in repr(summary) and 'admin' not in repr(summary)


def test_stop_before_start_does_not_connect():
    factory = lambda *a, **k: pytest.fail('must not connect')
    worker = EventWorker('192.0.2.1', '', '', session_factory=factory)
    worker.stop()
    worker.start()
    assert worker.wait()
    assert worker.snapshot().state == 'stopped'


def test_request_demultiplexes_interleaved_alarm_and_waits_after_short_timeout():
    session = EventSession('192.0.2.1','','')
    session.session = 1
    sent = []
    session.send_only = lambda *args: sent.append(args)
    replies = iter([socket.timeout(), (1504,1,{'AlarmInfo':{'Event':'VideoMotion','Status':'Start'}}), (1501,1,{'Ret':100})])
    def receive(deadline):
        item = next(replies)
        if isinstance(item,Exception): raise item
        return item
    session.receive = receive
    assert session.subscribe() == 'yes'
    assert len(session.pending) == 1
    assert sent[0][0] == 1500


def test_worker_reconnect_backoff_sanitizes_and_shutdown_closes_every_session():
    from collections import deque
    worker = EventWorker('192.0.2.1','admin','secret')
    sessions = []
    waits = []
    worker._stop.wait = lambda delay: waits.append(delay) or False
    class Session:
        session = 1
        def __init__(self):
            self.pending = deque()
            self.closed = False
            self.reads = 0
        def login(self):
            if len(sessions) < 3: raise OSError('password=secret')
            return {'Ret':100,'AliveInterval':20}
        def subscribe(self): return 'yes'
        def read_detection_summary(self): return ()
        def receive(self,deadline):
            self.reads += 1
            if self.reads == 1:
                return 1504,1,{'AlarmInfo':{'Event':'VideoMotion','Status':'Start','Channel':0,'Password':'secret'}}
            worker.stop()
            raise OSError('secret')
        def close(self): self.closed = True
    def factory(*a,**kw):
        session = Session()
        sessions.append(session)
        return session
    worker._factory = factory
    worker._run()
    assert waits == [1,2]
    assert all(session.closed for session in sessions)
    assert worker.events.get_nowait().kind == 'motion_start'
    assert 'secret' not in repr(worker.snapshot())
    assert worker.snapshot().state == 'stopped'
    worker.stop()


def test_unsupported_worker_never_reconnects():
    from collections import deque
    worker = EventWorker('192.0.2.1','','')
    class Session:
        pending = deque()
        def login(self): return {'Ret':100}
        def subscribe(self): return 'no'
        def close(self): pass
    worker._factory = lambda *a,**kw:Session()
    worker._stop.wait = lambda delay: pytest.fail('unsupported must not retry')
    worker._run()
    assert worker.snapshot().support == 'no'
    assert not worker.snapshot().active


def test_configuration_queries_only_read_allowlisted_names():
    session = EventSession('192.0.2.1','','')
    commands = []
    def get(code,payload):
        commands.append((code,payload['Name']))
        return {'Ret':100,payload['Name']:{'Enable':True,'Password':'secret'}}
    session._send_json = get
    summary = session.read_detection_summary()
    assert all(code == 1042 for code,name in commands)
    assert {name for code,name in commands} == {'Detect','Detect.MotionDetect','Detect.HumanDetection','Detect.HumanDetect'}
    assert 'secret' not in repr(summary)


def test_subscription_and_get_reject_active_payloads_even_with_allowed_id():
    session = EventSession('192.0.2.1','','')
    for code,payload in [(1500,{'Name':'OPNetAlarm','SessionID':'0x0'}), (1042,{'Name':'Detect','SessionID':'0x0','Enable':True}), (1042,{'Name':'OPMachine','SessionID':'0x0'})]:
        with pytest.raises(EventProtocolError,match='command_not_allowed'):
            session.send_only(code,payload)

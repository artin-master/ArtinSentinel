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

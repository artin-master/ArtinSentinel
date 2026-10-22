import json
import socket
import struct
import threading
import time

import pytest

from artin_sentinel.dvrip_field_probe import probe_dvrip_single_shot
from artin_sentinel.xm_dvrip import DvripSession, _HEADER


SESSION = 0x12345678


def _wire(message, payload=b"", *, session=SESSION, sequence=0):
    return _HEADER.pack(0xFF, 0, session, sequence, message, len(payload)) + payload


def _reply(message, body):
    return _wire(message, json.dumps(body, separators=(",", ":")).encode() + b"\n\x00")


def _video_chunk():
    # Small DVRIP H.264 keyframe packet; the diagnostic inspects only its header.
    media = bytearray(20)
    media[:4] = b"\x00\x00\x01\xfc"
    media[4] = 2
    media[12:16] = (4).to_bytes(4, "little")
    return _wire(1412, bytes(media))


class CaptureSocket:
    def __init__(self, claim_ret=100, media=True):
        self.sent = []
        self.closed = False
        self._closed = False
        self.incoming = bytearray(
            _reply(1000, {"Ret": 100, "SessionID": "0x12345678"})
            + _reply(1413, {"Ret": claim_ret})
            + (_video_chunk() if media else b"")
        )

    def sendall(self, packet):
        self.sent.append(bytes(packet))

    def recv(self, size):
        if not self.incoming:
            raise socket.timeout("simulated media timeout")
        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data

    def settimeout(self, _timeout):
        pass

    def close(self):
        self.closed = True
        self._closed = True


def _factory_for(sock, created=None):
    def factory(host, username, password, **kwargs):
        if created is not None:
            created.append(sock)
        return DvripSession(host, username, password, sock=sock, **kwargs)
    return factory


@pytest.mark.parametrize("channel", [0, 1, 2])
@pytest.mark.parametrize("subtype,stream", [(0, "Main"), (1, "Extra1")])
def test_single_shot_preserves_0291_login_claim_start_wire_and_order(channel, subtype, stream):
    sock = CaptureSocket()
    result = probe_dvrip_single_shot(
        "192.0.2.47", "operator", "secret", channel=channel, subtype=subtype,
        _session_factory=_factory_for(sock),
    )

    claim = (
        '{"Name":"OPMonitor","SessionID":"0x12345678","OPMonitor":{"Action":"Claim",'
        f'"Parameter":{{"Channel":{channel},"CombinMode":"NONE","StreamType":"{stream}",'
        '"TransMode":"TCP"}}}'
    ).encode() + b"\n\x00"
    start = claim.replace(b'"Action":"Claim"', b'"Action":"Start"')
    assert [
        (_HEADER.unpack(packet[:_HEADER.size])[4], _HEADER.unpack(packet[:_HEADER.size])[3], packet[_HEADER.size:])
        for packet in sock.sent
    ] == [
        (1000, 0, b'{"EncryptType":"MD5","LoginType":"DVRIP-Web","PassWord":"awAU3E4X","UserName":"operator"}\n\x00'),
        (1413, 1, claim),
        (1410, 2, start),
    ]
    assert [event.stage for event in result.events] == [
        "session_created", "connected", "login_ok", "claim_ok", "start_sent", "first_video_packet", "closed",
    ]
    assert result.login_ret == result.claim_ret == 100
    assert result.start_sent and result.first_video_packet
    assert result.codec == "h264"
    assert result.socket_closed and sock.closed


def test_claim_353_stops_before_start_and_closes_session():
    sock = CaptureSocket(claim_ret=353)
    result = probe_dvrip_single_shot(
        "192.0.2.47", "operator", "secret", channel=1, subtype=0,
        _session_factory=_factory_for(sock),
    )
    assert result.login_ret == 100
    assert result.claim_ret == 353
    assert result.error_code == "claim_rejected"
    assert not result.start_sent
    assert [_HEADER.unpack(packet[:_HEADER.size])[4] for packet in sock.sent] == [1000, 1413]
    assert result.socket_closed and sock.closed


def test_media_timeout_is_one_attempt_and_does_not_retry():
    sock = CaptureSocket(media=False)
    result = probe_dvrip_single_shot(
        "192.0.2.47", "operator", "secret", channel=2, subtype=1, timeout=0.1,
        _session_factory=_factory_for(sock),
    )
    assert result.error_code == "timeout"
    assert result.start_sent and not result.first_video_packet
    assert len(sock.sent) == 3
    assert result.socket_closed


def test_probe_rejects_parallel_attempt_and_second_session_starts_after_close():
    entered_read = threading.Event()
    release_read = threading.Event()
    created = []

    class BlockingSession:
        def __init__(self, index):
            self.index = index
            self.sock = self
            self.timeout = 0.1
            self.media_deadline = 0
            self.media_cancel = None
            self.closed = False
            self.login_reply_code = self.monitor_reply_code = 100

        def connect(self): pass
        def login(self): pass
        def monitor_claim(self, *_args): pass
        def monitor_start(self, *_args): pass
        def settimeout(self, _value): pass
        def read_media_packet(self):
            entered_read.set()
            release_read.wait(2)
            raise TimeoutError("field probe timeout")
        def close(self):
            self.closed = True
            self.sock = None

    def factory(*_args, **_kwargs):
        if created:
            assert created[-1].closed, "prior DVRIP session must close before the next is created"
        session = BlockingSession(len(created))
        created.append(session)
        return session

    first = threading.Thread(target=lambda: probe_dvrip_single_shot(
        "192.0.2.47", "operator", "secret", channel=1, subtype=0, timeout=1,
        _session_factory=factory,
    ))
    first.start()
    assert entered_read.wait(1)
    with pytest.raises(RuntimeError, match="sonda DVRIP"):
        probe_dvrip_single_shot(
            "192.0.2.47", "operator", "secret", channel=2, subtype=0,
            _session_factory=factory,
        )
    release_read.set()
    first.join(2)
    assert not first.is_alive()
    assert len(created) == 1
    assert created[0].closed

    # A later manual attempt creates a fresh session only after the first closed.
    probe_dvrip_single_shot(
        "192.0.2.47", "operator", "secret", channel=2, subtype=1, timeout=0.1,
        _session_factory=factory,
    )
    assert len(created) == 2
    assert created[1].closed


def test_experiment_module_has_no_discovery_database_or_ui_dependencies():
    from pathlib import Path
    import ast

    source = Path("artin_sentinel/dvrip_field_probe.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports.intersection({"db", "services", "app", "discovery", "ip_camera", "recorder"})

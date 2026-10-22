from __future__ import annotations

import json
import struct

import artin_sentinel.ptz as ptz
from artin_sentinel.akdb import ptz_capability
from artin_sentinel.xm_dvrip import DvripSession, sofia_hash, dvrip_ptz_command


class FakeSocket:
    def __init__(self, replies: list[dict]):
        self.sent = []
        self._buffer = bytearray()
        self.replies = list(replies)
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, packet: bytes):
        self.sent.append(packet)
        reply = self.replies.pop(0)
        payload = json.dumps(reply, separators=(",", ":")).encode() + b"\n\x00"
        sid = int(str(reply.get("SessionID", "0x0")), 16)
        header = struct.pack("<BB2xII2xHI", 0xFF, 0, sid, 1, 1001, len(payload))
        self._buffer.extend(header + payload)

    def recv(self, size):
        if not self._buffer:
            return b""
        out = bytes(self._buffer[:size])
        del self._buffer[:size]
        return out

    def close(self):
        pass


def test_sofia_hash_known_empty_password_vector():
    assert sofia_hash("") == "tlJwpbo6"


def test_itblue_x3_prefers_native_dvrip_backend_without_erasing_onvif_evidence():
    cap = ptz_capability(profile_key="it-blue-x3-we2q")
    assert cap["mode"] == "dvrip-confirmed"
    assert cap["backend"] == "dvrip"
    assert cap["direct_control"] is True
    assert cap["zoom"] is False


def test_dvrip_command_mapping_has_diagonals_and_zoom():
    assert dvrip_ptz_command("up-left") == "DirectionRightUp"
    assert dvrip_ptz_command("down-right") == "DirectionLeftDown"
    assert dvrip_ptz_command("zoom-in") == "ZoomTile"
    assert dvrip_ptz_command("zoom-out") == "ZoomWide"


def test_dvrip_login_and_ptz_packet_never_contains_plain_password(monkeypatch):
    fake = FakeSocket([
        {"Ret": 100, "SessionID": "0x0000002d", "AliveInterval": 21},
        {"Ret": 100, "SessionID": "0x0000002d"},
    ])
    monkeypatch.setattr("socket.create_connection", lambda *a, **k: fake)
    with DvripSession("192.0.2.10", "admin", "Secret-Example") as session:
        session.ptz("DirectionRight", step=4, start=True)
    joined = b"".join(fake.sent)
    assert b"Secret-Example" not in joined
    assert b"OPPTZControl" in joined
    assert b"DirectionRight" in joined
    assert b'"Preset":65535' in joined


def test_provider_router_calls_dvrip_backend(monkeypatch):
    calls = []
    monkeypatch.setattr("artin_sentinel.xm_dvrip.dvrip_ptz_start", lambda *a, **k: calls.append((a, k)) or "ok")
    assert ptz.start_move_provider("192.0.2.20", "u", "p", "", "left", backend="dvrip") == "ok"
    assert calls and calls[0][0][3] == "left"

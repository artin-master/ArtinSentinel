from pathlib import Path
from types import SimpleNamespace
import struct

import artin_sentinel.native_protocols as native
import artin_sentinel.recorder as recorder
import artin_sentinel.talkback as talkback
from artin_sentinel import __version__
from artin_sentinel.akdb import audio_capability, capability_map, recorder_scan_limit
from artin_sentinel.xm_dvrip import DvripSession, _HEADER
from artin_akdb import CORE_REVISION, record_by_legacy_key


def test_release_and_shared_akdb_0223():
    assert __version__ == "0.2.90"
    assert CORE_REVISION >= 6
    mhdx = capability_map(profile_key="intelbras-mhdx")
    assert mhdx["max_analog_channels"] == 4
    assert mhdx["max_ip_channels"] == 1
    assert mhdx["max_total_channels"] == 5
    assert recorder_scan_limit(provider="intelbras", profile_key="intelbras-mhdx") == 5
    audio = audio_capability(profile_key="it-blue-x3-we2q")
    assert audio["mode"] == "bidirectional"
    assert audio["talkback_protocol"] == "xm-dvrip-g711a-experimental"
    core = record_by_legacy_key("it-blue-x3-we2q")
    assert core is not None
    assert "xm-dvrip-talkback-g711a-experimental" in core.protocols
    assert "xm-dvrip-talkback-not-field-validated" in core.negative_knowledge


def test_intelbras_channel_title_cgi_parser(monkeypatch):
    payload = b"table.ChannelTitle[0].Name=Frente\r\ntable.ChannelTitle[4].Name=IP Extra\r\n"
    monkeypatch.setattr(native, "_intelbras_cgi_get", lambda *a, **k: (200, payload, "http://device", "OK"))
    inv = native.probe_intelbras_channel_titles("192.0.2.1", "admin", "pw")
    assert inv.authenticated and inv.ok
    assert [(r.channel_id, r.name) for r in inv.channels] == [(1, "Frente"), (5, "IP Extra")]


def test_mhdx_scan_includes_dedicated_ip_channel_5(monkeypatch):
    inv = SimpleNamespace(
        authenticated=True, ok=True, detail="CGI ChannelTitle listou 5 canal(is)",
        channels=tuple(SimpleNamespace(channel_id=i, name=f"Canal {i:02d}") for i in range(1, 6)),
    )
    monkeypatch.setattr(recorder, "probe_intelbras_channel_titles", lambda *a, **k: inv)
    monkeypatch.setattr(recorder, "_select_stream_profile", lambda *a, **k: (5, 0, "RTSP confirmado", "rtsp://seed"))
    calls = []
    def probe(url, *a, **k):
        calls.append(url)
        ok = "channel=5" in url
        return recorder.RtspProbeReport(ok, 200 if ok else 404, "ok" if ok else "no")
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", probe)
    monkeypatch.setattr(recorder, "_audio_fields_for_urls", lambda *a, **k: {})
    rows = recorder.scan_intelbras_channels("192.0.2.2", "admin", "pw", max_channels=5)
    assert [r.channel for r in rows] == [1, 2, 3, 4, 5]
    ch5 = next(r for r in rows if r.channel == 5)
    assert ch5.available is True
    assert ch5.channel_kind == "ip"
    assert any("channel=5" in u for u in calls)


def test_itblue_multilens_includes_short_numeric_aliases():
    source = Path("artin_sentinel/ip_camera.py").read_text(encoding="utf-8")
    assert 'f"rtsp://{ip}:554/{numeric}"' in source
    assert 'f"RTSP curto /{numeric}"' in source
    assert "visual" in source.lower() and "dedup" in source.lower()


def test_dvrip_talk_control_and_audio_packet(monkeypatch):
    session = DvripSession("192.0.2.47", "admin", "secret")
    session.session = 0x10203040
    calls = []
    def fake_json(self, msgid, payload, **kwargs):
        calls.append((msgid, payload))
        return {"Ret": 100}
    monkeypatch.setattr(DvripSession, "_send_json", fake_json)
    session.talk_claim(); session.talk_start(); session.talk_stop()
    assert [m for m, _ in calls] == [1434, 1430, 1430]
    assert calls[0][1]["OPTalk"]["AudioFormat"]["EncodeType"] == "G711_ALAW"
    assert calls[0][1]["OPTalk"]["AudioFormat"]["SampleRate"] == 8
    assert "AudioFormat" not in calls[1][1]["OPTalk"]
    assert "AudioFormat" not in calls[2][1]["OPTalk"]

    class Sock:
        def __init__(self): self.data = b""
        def sendall(self, data): self.data += data
    sock = Sock(); session.sock = sock
    session.send_talk_audio(b"abc")
    header = sock.data[:_HEADER.size]
    magic, _version, sid, seq, msgid, length = _HEADER.unpack(header)
    body = sock.data[_HEADER.size:]
    assert magic == 0xFF and sid == 0x10203040 and msgid == 1432
    assert seq == 0
    assert length == len(body)
    assert body.startswith(b"\x00\x00\x01\xfa\x0e\x02\x40\x01")
    assert body.endswith(b"abc")


def test_talkback_capture_is_mono_8k_g711a(monkeypatch):
    monkeypatch.setattr(talkback.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(talkback, "ffmpeg_microphone_inputs", lambda: frozenset({"pulse"}))
    sess = talkback.XmDvripTalkbackSession(
        "192.0.2.47", "admin", "pw", microphone_label="Pulse/PipeWire"
    )
    commands = sess._capture_commands()
    assert commands and commands[0][0] == "Pulse/PipeWire"
    cmd = commands[0][1]
    assert ["-ac", "1"] == cmd[cmd.index("-ac"):cmd.index("-ac") + 2]
    assert ["-ar", "8000"] == cmd[cmd.index("-ar"):cmd.index("-ar") + 2]
    assert ["-c:a", "pcm_alaw"] == cmd[cmd.index("-c:a"):cmd.index("-c:a") + 2]


def test_main_live_ptt_has_explicit_start_stop_control_and_stops_with_tile():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "self.talkback_btn.setCheckable(True)" in source
    assert "self.talkback_btn.clicked.connect(self.toggle_selected_talkback)" in source
    assert "def stop_talkback" in source
    block = source[source.index("    def stop_tile_stream(self, tile: VideoTile):"):source.index("    def stop_all_live_streams", source.index("    def stop_tile_stream(self, tile: VideoTile):"))]
    assert "self.talkback_tile_index == tile.index" in block
    assert "self.stop_talkback()" in block

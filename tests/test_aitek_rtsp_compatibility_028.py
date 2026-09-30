from types import SimpleNamespace

import artin_sentinel.live as live
import artin_sentinel.recorder as recorder
from artin_sentinel.ip_camera import _candidate_pairs, direct_camera_provider_hint


def test_manual_aitek_identity_guides_read_only_provider_probe():
    assert direct_camera_provider_hint("generic-onvif", "Aitek", "IP CAMERA", "Câmera") == "aitek"
    assert direct_camera_provider_hint("generic-onvif", "", "", "Aitek Portão") == "aitek"


def test_aitek_candidates_cover_field_firmware_families_without_real_secret():
    pairs = _candidate_pairs("192.0.2.21", "aitek")
    flat = "\n".join(" ".join(x for x in pair if x) for pair in pairs)
    assert "rtsp://192.0.2.21:554/" in flat
    assert "/ch01/0" in flat
    assert "/ch0/stream0" in flat
    assert "_channel=1_stream=0.sdp?real_stream" in flat
    assert "&channel=1&stream=0.sdp?real_stream" in flat
    assert "{username}" in flat and "{password}" in flat
    assert "supersecret" not in flat


def test_live_direct_camera_can_fallback_transport(monkeypatch):
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(live, "ffmpeg_rtsp_timeout_args", lambda: ())
    sess = live.LiveStreamSession("rtsp://192.0.2.21/live", transport_fallback=True)
    assert sess.transport_fallback is True
    tcp = sess._command(sess.url, "tcp")
    udp = sess._command(sess.url, "udp")
    assert tcp[tcp.index("-rtsp_transport") + 1] == "tcp"
    assert udp[udp.index("-rtsp_transport") + 1] == "udp"


def test_ffprobe_retries_udp_when_tcp_transport_is_not_accepted(monkeypatch):
    calls = []
    monkeypatch.setattr(recorder.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(recorder, "ffprobe_rtsp_timeout_args", lambda: ())

    def fake_run(cmd, **kwargs):
        transport = cmd[cmd.index("-rtsp_transport") + 1]
        calls.append(transport)
        if transport == "tcp":
            return SimpleNamespace(returncode=1, stdout="", stderr="461 Unsupported transport")
        return SimpleNamespace(returncode=0, stdout='{"streams":[{"codec_name":"h264","width":1280,"height":720}]}', stderr="")

    monkeypatch.setattr(recorder.subprocess, "run", fake_run)
    ok, detail = recorder.validate_rtsp_media("rtsp://192.0.2.21:554/ch01/0", "admin", "pw")
    assert ok is True
    assert calls == ["tcp", "udp"]
    assert "UDP" in detail

from pathlib import Path
import re

import artin_sentinel.ip_camera as ip_camera
from artin_sentinel import __version__
from artin_sentinel.live import ordered_audio_urls


def test_version_0212():
    assert __version__ == "0.2.93"


def test_audio_candidates_try_active_then_other_profile():
    main = "rtsp://cam/main"
    sub = "rtsp://cam/sub"
    legacy = "rtsp://cam/legacy"
    assert ordered_audio_urls(main, sub, legacy, "sub") == [sub, main, legacy]
    assert ordered_audio_urls(main, sub, legacy, "main") == [main, sub, legacy]


def test_audio_candidates_are_unique_when_legacy_matches_main():
    main = "rtsp://cam/main"
    assert ordered_audio_urls(main, "", main, "sub") == [main]


def test_itblue_x3_multilens_accepts_three_distinct_rtsp_lenses(monkeypatch):
    monkeypatch.setattr(ip_camera, "dvrip_multilens_hints", lambda *a, **k: {})
    monkeypatch.setattr(ip_camera, "probe_dvrip_media", lambda *a, **k: type("Probe", (), {"ok": False})())
    monkeypatch.setattr(ip_camera, "_video_frame_signature", lambda *a, **k: None)
    def fake_validate(url, username, password, **kwargs):
        # Only the native XM underscore path is considered valid in this test.
        ok = "_channel=" in url
        return ok, "ffprobe h265" if ok else "404"

    def fake_fingerprint(url, username, password, timeout=8.0):
        m = re.search(r"_channel=(\d+)_", url)
        return (f"{int(m.group(1)) + 1:064x}" if m else "")

    monkeypatch.setattr(ip_camera, "validate_rtsp_media", fake_validate)
    monkeypatch.setattr(ip_camera, "_video_frame_fingerprint", fake_fingerprint)
    monkeypatch.setattr(ip_camera, "_direct_audio_fields", lambda *a, **k: {
        "audio_mode": "bidirectional", "audio_codec": "", "audio_sample_rate": 0,
        "audio_channels": 0, "audio_detail": "",
    })

    channels = ip_camera._scan_itblue_x3_multilens_rtsp("192.0.2.51", "u", "p")
    assert [ch.channel for ch in channels] == [1, 2, 3]
    assert [ch.name for ch in channels] == ["Câmera 01", "Câmera 02", "Câmera 03"]


def test_itblue_x3_multilens_drops_aliases(monkeypatch):
    monkeypatch.setattr(ip_camera, "dvrip_multilens_hints", lambda *a, **k: {})
    monkeypatch.setattr(ip_camera, "probe_dvrip_media", lambda *a, **k: type("Probe", (), {"ok": False})())
    monkeypatch.setattr(ip_camera, "_video_frame_signature", lambda *a, **k: None)
    monkeypatch.setattr(ip_camera, "validate_rtsp_media", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(ip_camera, "_video_frame_fingerprint", lambda *a, **k: "a" * 64)
    monkeypatch.setattr(ip_camera, "_direct_audio_fields", lambda *a, **k: {
        "audio_mode": "bidirectional", "audio_codec": "", "audio_sample_rate": 0,
        "audio_channels": 0, "audio_detail": "",
    })
    channels = ip_camera._scan_itblue_x3_multilens_rtsp("192.0.2.51", "u", "p")
    assert len(channels) == 1


def test_live_ui_has_drag_reorder_and_active_stream_indicator():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "moveRequested = Signal(object, object)" in text
    assert "swap_content_with" in text
    assert "move_tile_source" in text
    assert "stream_badge" in text
    assert "● MAIN em uso" in text
    assert "● SUBSTREAM em uso" in text
    assert 'act.setCheckable(True)' in text
    assert 'act.setChecked(mode == active_kind or (mode == "auto" and not active_kind))' in text


def test_audio_session_preflights_main_sub_before_claiming_active():
    text = Path("artin_sentinel/live.py").read_text(encoding="utf-8")
    assert "Áudio: procurando faixa no Main/Sub" in text
    assert "probe_rtsp_media_capabilities" in text
    assert "Áudio confirmado" in text
    assert "Sem faixa de áudio nos streams Main/Sub" in text

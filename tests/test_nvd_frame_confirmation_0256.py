from types import SimpleNamespace

import pytest

from artin_sentinel import recorder


def test_nvd_listed_channels_need_a_decoded_frame(monkeypatch):
    inventory = SimpleNamespace(
        channels=[SimpleNamespace(channel_id=ch, name=f"CAM {ch}") for ch in (1, 2)],
        ok=True, authenticated=True, detail="inventário autenticado",
    )
    monkeypatch.setattr(recorder, "probe_intelbras_channel_titles", lambda *_a, **_kw: inventory)
    monkeypatch.setattr(recorder, "_select_stream_profile", lambda *_a, **_kw: (1, 0, "SDP OK", "rtsp://seed"))
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", lambda *_a, **_kw:
                        recorder.RtspProbeReport(True, 200, "SDP OK", first_status=200))
    monkeypatch.setattr(recorder, "confirm_nvr_video_frame", lambda url, *_a:
                        (True, "quadro decodificado") if "channel=2" in url and "subtype=0" in url
                        else (False, "RTSP sem quadro de vídeo"))
    monkeypatch.setattr(recorder, "_audio_fields_for_urls", lambda *_a, **_kw: {})

    rows = recorder.scan_intelbras_channels("192.0.2.151", "admin", "secret", max_channels=2, channel_layout="nvr")
    assert len(rows) == 2
    assert not rows[0].available and "sem quadro" in rows[0].detail
    assert rows[1].available and "channel=2" in rows[1].main_rtsp_url
    assert not rows[1].sub_rtsp_url


def test_nvr_inventory_does_not_open_black_mosaic_but_mhdx_keeps_legacy_fallback():
    rows = [{"available": 0, "id": 1}, {"available": 0, "id": 2}]
    assert recorder.channels_for_live_view(rows, "nvr") == []
    assert recorder.channels_for_live_view(rows, "dvr") == rows
    rows[1]["available"] = 1
    assert recorder.channels_for_live_view(rows, "nvr") == [rows[1]]


def test_nvd_frame_probe_requires_actual_decoded_bytes_and_sanitizes_error(monkeypatch):
    seen = []
    monkeypatch.setattr(recorder.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(recorder, "ffmpeg_rtsp_timeout_args", lambda: ())

    def run(command, **_kwargs):
        seen.append(command)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"secret-in-stderr")

    monkeypatch.setattr(recorder.subprocess, "run", run)
    ok, detail = recorder.confirm_nvr_video_frame("rtsp://192.0.2.151/cam/realmonitor?channel=1&subtype=0", "admin", "secret")
    assert not ok and "secret" not in detail
    assert "secret" in " ".join(seen[0])
    assert "-frames:v" in seen[0] and "-rtsp_transport" in seen[0]

    monkeypatch.setattr(recorder.subprocess, "run", lambda *_a, **_kw:
                        SimpleNamespace(returncode=0, stdout=b"\x80" * 256, stderr=b""))
    assert recorder.confirm_nvr_video_frame("rtsp://192.0.2.151/live", "admin", "secret")[0]


def test_nvr_auth_diagnostic_cites_both_probes_without_exposing_password(monkeypatch):
    monkeypatch.setattr(recorder, "probe_intelbras_channel_titles", lambda *_a, **_kw:
                        SimpleNamespace(channels=(), ok=False, authenticated=False,
                                        status_code=401, detail="CGI HTTP 401"))
    monkeypatch.setattr(recorder, "_select_stream_profile", lambda *_a, **_kw:
                        (_ for _ in ()).throw(recorder.RtspAuthenticationError("RTSP 401; ffprobe não confirmou")))
    with pytest.raises(recorder.RtspAuthenticationError) as raised:
        recorder.scan_intelbras_channels("192.0.2.151", "admin", "secret", max_channels=16,
                                        channel_layout="nvr")
    message = str(raised.value)
    assert "RTSP 401" in message and "HTTP" in message and "401" in message
    assert "secret" not in message

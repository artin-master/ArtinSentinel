import json
from pathlib import Path
from types import SimpleNamespace

from artin_sentinel.akdb import public_summary, capability_map
from artin_sentinel.db import Database
from artin_sentinel.device_intelligence import resolve_operational_identity, recorder_provider_hint
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.providers import pick_provider
import artin_sentinel.live as live
import artin_sentinel.recorder as recorder


def test_akdb_exposes_first_class_canonical_equipment_type():
    rows = {row["key"]: row for row in public_summary()}
    assert rows["hikvision-ds-7216hghi-f1"]["canonical_type"] == "dvr"
    assert rows["it-blue-x3-we2q"]["canonical_type"] == "camera-ptz"
    assert rows["intelbras-vipc-1230-d-g2"]["canonical_type"] == "camera-fixed"
    assert capability_map(profile_key="hikvision-ds-7216hghi-f1")["canonical_type"] == "dvr"


def test_manual_override_is_persisted_separately_and_wins_routing(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site = int(db.list_sites()[0]["id"])
    device_id = db.upsert_device(Device(
        site_id=site, name="Hikvision", ip="192.0.2.60", manufacturer="Hikvision",
        model="", kind=DeviceKind.CAMERA, provider="hikvision",
    ))
    db.update_device_identity(device_id, "DVR Hikvision", "dvr", "Hikvision", "DS-7216HGHI-F1")
    row = db.get_device(device_id)
    assert row["detected_kind"] == "camera"
    assert row["manual_kind"] == "dvr"
    assert row["kind"] == "dvr"
    ident = resolve_operational_identity(row)
    assert ident.kind == "dvr"
    assert ident.source == "operator"
    assert recorder_provider_hint(row, ident) == "hikvision"
    db.close()


def test_exact_akdb_profile_routes_hikvision_as_recorder_without_manual_override():
    metadata = json.dumps({"akdb_profile": "hikvision-ds-7216hghi-f1"})
    row = {
        "kind": "unknown", "detected_kind": "unknown", "manual_kind": "", "identity_locked": 0,
        "metadata_json": metadata, "provider": "hikvision", "detected_provider": "hikvision",
        "manufacturer": "Hikvision", "model": "DS-7216HGHI-F1", "name": "DVR",
        "detected_manufacturer": "Hikvision", "detected_model": "DS-7216HGHI-F1",
    }
    ident = resolve_operational_identity(row)
    assert ident.kind == "dvr"
    assert ident.canonical_type == "dvr"
    assert ident.source == "akdb"


def test_provider_classification_uses_specific_akdb_canonical_type():
    dev = Device(
        site_id=1, name="Hikvision DVR", ip="192.0.2.60", kind=DeviceKind.UNKNOWN,
        manufacturer="Hikvision", model="DS-7216HGHI-F1",
        metadata={"open_ports": [80, 554, 8000], "evidence": ["Hikvision"]},
    )
    pick_provider(dev)
    assert dev.provider == "hikvision"
    assert dev.kind == DeviceKind.DVR
    assert dev.metadata["akdb_profile"] == "hikvision-ds-7216hghi-f1"


def test_audio_backend_order_falls_back_beyond_ffplay(monkeypatch):
    live.ffmpeg_audio_output_devices.cache_clear()
    monkeypatch.setattr(live.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"ffplay", "ffmpeg"} else None)
    monkeypatch.setattr(live, "ffmpeg_audio_output_devices", lambda: frozenset({"pulse", "alsa"}))
    monkeypatch.setattr(live, "ffmpeg_rtsp_timeout_args", lambda: ())
    session = live.LiveAudioSession("rtsp://camera/main", "admin", "secret", 70)
    commands = session._commands("rtsp://camera/main", "tcp")
    assert [name for name, _ in commands] == ["FFmpeg/Pulse-PipeWire", "FFmpeg/ALSA", "ffplay/SDL"]
    assert any("pulse" in cmd for name, cmd in commands if name == "FFmpeg/Pulse-PipeWire")


def test_recorder_audio_probe_persists_real_track(monkeypatch):
    monkeypatch.setattr(recorder, "probe_rtsp_media_capabilities", lambda *a, **k: SimpleNamespace(
        ok=True, has_audio=True, audio_codec="pcm_alaw", audio_sample_rate=8000,
        audio_channels=1, detail="vídeo=h264 • áudio=pcm_alaw 8000 Hz",
    ))
    fields = recorder._audio_fields_for_urls(["rtsp://dvr/ch1"], "admin", "secret")
    assert fields["audio_mode"] == "listen"
    assert fields["audio_codec"] == "pcm_alaw"
    assert fields["audio_sample_rate"] == 8000


def test_hikvision_rtsp_failure_reports_when_isapi_validated_password(monkeypatch):
    monkeypatch.setattr(recorder, "probe_hikvision_isapi_device_info", lambda *a, **k: SimpleNamespace(
        authenticated=True, status_code=200, manufacturer="Hikvision", model="DS-7216HGHI-F1", detail="OK"
    ))
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", lambda *a, **k: recorder.RtspProbeReport(False, 404, "Not Found"))
    try:
        recorder.scan_hikvision_channels("192.0.2.60", "admin", "correct", max_channels=1)
    except recorder.RtspCompatibilityError as exc:
        text = str(exc)
    else:
        raise AssertionError("expected compatibility error")
    assert "credencial foi aceita pela ISAPI" in text
    assert "senha foi validada" in text


def test_0214_ui_has_akdb_type_and_redesigned_ptz_console():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "Tipo de equipamento" in text
    assert "PtzPanel" in text
    assert '("stop", "STOP"' in text
    assert "Pulse/PipeWire" in text
    assert "Roteamento:" in text


def test_hikvision_scan_does_not_require_active_channel_in_first_four(monkeypatch):
    monkeypatch.setattr(recorder, "probe_hikvision_isapi_device_info", lambda *a, **k: SimpleNamespace(
        authenticated=True, status_code=200, manufacturer="Hikvision", model="DS-7216HGHI-F1", detail="OK"
    ))
    def fake_probe(url, *args, **kwargs):
        ok = "/Streaming/Channels/501" in url
        return recorder.RtspProbeReport(ok, 200 if ok else 404, "OK" if ok else "Not Found")
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", fake_probe)
    monkeypatch.setattr(recorder, "_audio_fields_for_urls", lambda *a, **k: {
        "audio_mode": "unknown", "audio_codec": "", "audio_sample_rate": 0,
        "audio_channels": 0, "audio_detail": "",
    })
    rows = recorder.scan_hikvision_channels("192.0.2.60", "admin", "correct", max_channels=5)
    available = [row.channel for row in rows if row.available]
    assert available == [5]


import pytest as _pytest
from types import SimpleNamespace as _NS
@_pytest.fixture(autouse=True)
def _configured_ip_inventory_stub(monkeypatch):
    import artin_sentinel.recorder as _recorder
    monkeypatch.setattr(_recorder, 'probe_hikvision_input_proxy_channels',
                        lambda *a, **k: _NS(channels=(), detail='sem entradas configuradas'))

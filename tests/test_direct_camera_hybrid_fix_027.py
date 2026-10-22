from pathlib import Path

from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind, DeviceStatus
from artin_sentinel.ip_camera import _candidate_pairs, DirectCameraScanResult
from artin_sentinel.live import authenticated_rtsp_url, sanitize_text, LiveStreamSession
from artin_sentinel.recorder import RecorderChannel, materialize_rtsp_template


def test_mibo_and_aitek_candidate_paths_are_bounded_and_safe_templates():
    mibo = _candidate_pairs("192.0.2.10", "intelbras-mibo")
    flat = "\n".join(" ".join(x for x in pair if x) for pair in mibo)
    assert "cam/realmonitor?channel=1&subtype=0" in flat
    assert "/live/mpeg4" in flat

    aitek = _candidate_pairs("192.0.2.11", "aitek")
    flat = "\n".join(" ".join(x for x in pair if x) for pair in aitek)
    assert "/ch01/0" in flat
    assert "/ch0/stream0" in flat
    assert "{password}" in flat
    assert "secret" not in flat


def test_credential_template_materializes_only_in_memory_and_is_sanitized():
    template = "rtsp://192.0.2.11:554/user={username}_password={password}_channel=1_stream=0.sdp"
    actual = materialize_rtsp_template(template, "admin", "s ecret")
    assert "{password}" not in actual
    assert "s%20ecret" in actual
    live = authenticated_rtsp_url(template, "admin", "s ecret")
    assert "s%20ecret" in live
    assert "<redacted>" in sanitize_text(live)


def test_manual_identity_is_separate_from_detected_identity(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(
        site_id=site, name="Possível CFTV", ip="192.0.2.20",
        manufacturer="", model="", kind=DeviceKind.NVR,
        provider="generic-onvif", status=DeviceStatus.ONLINE,
    ))
    db.update_device_identity(did, "MiboCam", "camera", "Intelbras", "iMX C")
    db.upsert_device(Device(
        site_id=site, name="Auto detect", ip="192.0.2.20",
        manufacturer="Generic", model="NVR-ish", kind=DeviceKind.NVR,
        provider="generic-onvif", status=DeviceStatus.ONLINE,
    ))
    row = db.get_device(did)
    assert row["manufacturer"] == "Intelbras"
    assert row["model"] == "iMX C"
    assert row["kind"] == "camera"
    assert row["detected_manufacturer"] == "Generic"
    assert row["detected_model"] == "NVR-ish"
    assert row["detected_kind"] == "nvr"
    assert row["identity_locked"] == 1
    db.close()


def test_failed_direct_validation_marks_old_stream_unavailable(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(site_id=site, name="Cam", ip="192.0.2.30", kind=DeviceKind.CAMERA))
    db.replace_recorder_channels(did, [RecorderChannel(
        1, "Câmera 01", "rtsp://192.0.2.30:554/live", True,
        source_name="Câmera 01", main_rtsp_url="rtsp://192.0.2.30:554/live",
        route_kind="direct", channel_kind="ip",
    )])
    db.invalidate_direct_camera_channels(did)
    row = db.list_recorder_channels(did)[0]
    assert row["available"] == 0
    assert "não validado" in row["detail"]
    db.close()


def test_direct_camera_sessions_can_stop_after_initial_failures():
    sess = LiveStreamSession("rtsp://192.0.2.42/live", stop_after_initial_failures=3)
    assert sess.stop_after_initial_failures == 3

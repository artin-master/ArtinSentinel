from pathlib import Path
from types import SimpleNamespace

from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.live import authenticated_rtsp_url, FRAME_SIZE


def test_authenticated_rtsp_url_encodes_credentials_without_changing_path():
    url = "rtsp://192.0.2.10:554/cam/realmonitor?channel=1&subtype=1"
    result = authenticated_rtsp_url(url, "admin@example", "p@ss:word")
    assert "admin%40example:p%40ss%3Aword@192.0.2.10:554" in result
    assert result.endswith("/cam/realmonitor?channel=1&subtype=1")


def test_live_frame_size_is_fixed_rgb_640x360():
    assert FRAME_SIZE == 640 * 360 * 3


def test_channel_alias_and_stream_preference_survive_rescan(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(site_id=site, name="Intelbras", ip="192.168.1.20"))
    first = [SimpleNamespace(
        channel=1,
        name="Canal 01",
        source_name="Canal 01",
        rtsp_url="rtsp://x/main",
        main_rtsp_url="rtsp://x/main",
        sub_rtsp_url="rtsp://x/sub",
        available=True,
        detail="OK",
    )]
    db.replace_recorder_channels(did, first)
    row = db.list_recorder_channels(did)[0]
    db.update_channel_alias(row["id"], "Portão")
    db.update_channel_preferred_stream(row["id"], "sub")

    second = [SimpleNamespace(
        channel=1,
        name="Entrada DVR",
        source_name="Entrada DVR",
        rtsp_url="rtsp://x/main2",
        main_rtsp_url="rtsp://x/main2",
        sub_rtsp_url="rtsp://x/sub2",
        available=True,
        detail="OK2",
    )]
    db.replace_recorder_channels(did, second)
    updated = db.list_recorder_channels(did)[0]
    assert updated["alias"] == "Portão"
    assert updated["source_name"] == "Entrada DVR"
    assert updated["preferred_stream"] == "sub"
    assert updated["main_rtsp_url"] == "rtsp://x/main2"
    assert updated["sub_rtsp_url"] == "rtsp://x/sub2"
    assert db.channel_display_name(updated) == "Portão"
    db.close()


def test_friendly_device_name_survives_discovery_upsert(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(
        site_id=site,
        name="Intelbras",
        ip="192.168.15.254",
        manufacturer="Intelbras",
        model="MHDX 1004",
        kind=DeviceKind.XVR,
        provider="intelbras",
    ))
    db.update_device_identity(did, "DVR Casa", "xvr", "Intelbras", "MHDX 1004")
    db.upsert_device(Device(
        site_id=site,
        name="Intelbras MHDX 1004",
        ip="192.168.15.254",
        manufacturer="Intelbras",
        model="MHDX 1004",
        kind=DeviceKind.XVR,
        provider="intelbras",
    ))
    row = db.get_device(did)
    assert row["name"] == "DVR Casa"
    assert row["detected_name"] == "Intelbras MHDX 1004"
    assert row["name_locked"] == 1
    db.close()


def test_password_is_not_a_device_sqlite_column(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(devices)")}
    assert "password" not in cols
    assert "secret" not in cols
    assert "credential_username" in cols
    assert "credential_saved" in cols
    db.close()

from pathlib import Path

from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind


def test_device_identity_can_be_corrected_without_recreating_device(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site_id = db.list_sites()[0]["id"]
    device_id = db.upsert_device(
        Device(
            site_id=site_id,
            name="Intelbras",
            ip="192.168.15.254",
            manufacturer="intelbras",
            model="Intelbras",
            kind=DeviceKind.XVR,
            provider="intelbras",
        )
    )

    db.update_device_identity(device_id, "DVR Escritório", "xvr", "Intelbras", "MHDX 1004")
    row = db.get_device(device_id)

    assert row["name"] == "DVR Escritório"
    assert row["kind"] == "xvr"
    assert row["manufacturer"] == "Intelbras"
    assert row["model"] == "MHDX 1004"
    db.close()

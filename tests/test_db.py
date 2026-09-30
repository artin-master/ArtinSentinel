from pathlib import Path
from artin_sentinel.db import Database
from artin_sentinel.domain import Device

def test_database_roundtrip(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    site = db.list_sites()[0]["id"]
    device_id = db.upsert_device(
        Device(site_id=site, name="Cam 1", ip="192.0.2.10")
    )
    assert db.get_device(device_id)["name"] == "Cam 1"
    db.update_device_status(device_id, "online")
    assert db.get_device(device_id)["status"] == "online"
    assert any(e["event_type"] == "device_online" for e in db.list_events())
    db.close()

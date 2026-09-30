from pathlib import Path
from types import SimpleNamespace
from artin_sentinel.db import Database
from artin_sentinel.domain import Device


def test_channel_persistence(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(site_id=site, name="DVR", ip="192.168.1.20"))
    channels = [SimpleNamespace(channel=1, name="Canal 01", rtsp_url="rtsp://x/1", available=True, detail="SDP OK")]
    db.replace_recorder_channels(did, channels)
    rows = db.list_recorder_channels(did)
    assert len(rows) == 1
    assert rows[0]["channel_no"] == 1
    assert rows[0]["detail"] == "SDP OK"
    db.close()

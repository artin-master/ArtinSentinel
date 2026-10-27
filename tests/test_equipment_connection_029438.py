import json
import pytest

from artin_sentinel.db import Database


def _device(db,site,ip,name="DVR"):
    now="2026-10-27T10:00:00+00:00"
    cur=db.conn.execute(
        "INSERT INTO devices(site_id,name,ip,kind,provider,status,metadata_json,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (site,name,ip,"dvr","generic","unknown","{}",now,now),
    )
    db.conn.commit()
    return int(cur.lastrowid)


def test_update_connection_reuses_same_record(tmp_path):
    db=Database(tmp_path/"sentinel.db")
    try:
        site=db.add_site("Mallet")
        did=_device(db,site,"192.0.2.10")
        db.update_device_connection(
            did,ip="192.0.2.11",provider="hikvision",
            web_url="http://192.0.2.11",rtsp_url="rtsp://192.0.2.11",
            metadata_patch={"recorder_rtsp_port":554,"hik_sdk":{"port":8000}},
        )
        rows=db.list_devices(site)
        assert len(rows)==1
        row=db.get_device(did)
        assert row["ip"]=="192.0.2.11"
        assert row["provider"]=="hikvision"
        meta=json.loads(row["metadata_json"])
        assert meta["hik_sdk"]["port"]==8000
    finally:
        db.close()


def test_update_connection_rejects_duplicate_site_ip(tmp_path):
    db=Database(tmp_path/"sentinel.db")
    try:
        site=db.add_site("Mallet")
        first=_device(db,site,"192.0.2.10","A")
        _device(db,site,"192.0.2.11","B")
        with pytest.raises(ValueError,match="Já existe"):
            db.update_device_connection(first,ip="192.0.2.11")
        assert db.get_device(first)["ip"]=="192.0.2.10"
    finally:
        db.close()

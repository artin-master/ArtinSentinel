from artin_sentinel.db import Database
from artin_sentinel.config_portability import export_configuration, import_configuration, preview_configuration
from artin_sentinel.import_onboarding import (
    configuration_devices, target_device_ids, device_needs_setup, devices_needing_setup,
)


def _add(db, site, ip, name, manufacturer="Hikvision", provider="hikvision"):
    now="2026-10-26T12:00:00+00:00"
    cur=db.conn.execute(
        "INSERT INTO devices(site_id,name,ip,manufacturer,model,kind,provider,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (site,name,ip,manufacturer,"DVR-TEST","dvr",provider,"unknown",now,now),
    )
    did=int(cur.lastrowid)
    db.conn.execute(
        "INSERT INTO recorder_channels(device_id,channel_no,name,alias,preferred_stream,updated_at) VALUES(?,?,?,?,?,?)",
        (did,1,"CAM 1","Entrada","auto",now),
    )
    db.conn.commit()
    return did


def test_all_sites_inventory_reveals_device_outside_active_site(tmp_path):
    db=Database(tmp_path/"inventory.db")
    try:
        a=db.add_site("Notebook")
        b=db.add_site("Mallet")
        first=_add(db,a,"192.0.2.1","Local")
        imported=_add(db,b,"192.0.2.2","DVR Mallet")
        assert [int(row["id"]) for row in configuration_devices(db,a,"active")] == [first]
        ids={int(row["id"]) for row in configuration_devices(db,a,"all")}
        assert {first,imported} <= ids
    finally:
        db.close()


def test_import_preview_resolves_existing_target_for_resume(tmp_path):
    source=Database(tmp_path/"source.db");target=Database(tmp_path/"target.db")
    try:
        sid=source.add_site("Mallet")
        _add(source,sid,"192.0.2.20","Hik DVR")
        payload=export_configuration(source)
        assert import_configuration(target,payload)["devices"]==1
        post=preview_configuration(target,payload)
        ids=target_device_ids(post)
        assert len(ids)==1
        assert target.get_device(ids[0])["name"]=="Hik DVR"
        assert device_needs_setup(target,ids[0])
        assert devices_needing_setup(target,ids)==ids
    finally:
        source.close();target.close()


def test_validated_credentials_and_route_finish_import_setup(tmp_path):
    db=Database(tmp_path/"ready.db")
    try:
        sid=db.add_site("Mallet");did=_add(db,sid,"192.0.2.30","DVR")
        db.conn.execute(
            "UPDATE devices SET credential_saved=1,credential_username='admin' WHERE id=?",(did,)
        )
        db.conn.execute(
            "UPDATE recorder_channels SET rtsp_url=?,main_rtsp_url=? WHERE device_id=?",
            ("rtsp://192.0.2.30/Streaming/Channels/101","rtsp://192.0.2.30/Streaming/Channels/101",did),
        )
        db.conn.commit()
        assert not device_needs_setup(db,did)
    finally:
        db.close()

from types import SimpleNamespace

import pytest

from artin_sentinel.db import Database
from artin_sentinel.config_portability import export_configuration, import_configuration, preview_configuration
from artin_sentinel.secure_transfer import (
    SecureTransferError,
    encrypt_bundle,
    decrypt_bundle,
    is_secure_bundle,
    collect_credentials,
    restore_credentials,
)


class MemoryCredentialStore:
    def __init__(self):
        self.data = {}
    def get_password(self, device_id):
        return self.data.get(int(device_id))
    def set_password(self, device_id, password):
        self.data[int(device_id)] = password
        return SimpleNamespace(ok=True, message="ok")


def _add(db, site, ip, name="DVR", username="admin", saved=True):
    now="2026-10-27T10:00:00+00:00"
    cur=db.conn.execute(
        "INSERT INTO devices(site_id,name,ip,manufacturer,model,kind,provider,status,credential_username,credential_saved,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (site,name,ip,"Hikvision","DS-TEST","dvr","hikvision","unknown",username,1 if saved else 0,now,now),
    )
    db.conn.commit()
    return int(cur.lastrowid)


def test_secure_bundle_round_trip_and_wrong_password():
    payload={"format":"demo","sites":[{"name":"Mallet"}]}
    credentials={"mallet\x1f192.0.2.1":{"username":"admin","password":"private-value"}}
    raw=encrypt_bundle(payload,credentials,"Transfer-Strong-123")
    assert is_secure_bundle(raw)
    assert b"private-value" not in raw
    decoded, secrets=decrypt_bundle(raw,"Transfer-Strong-123")
    assert decoded==payload
    assert secrets==credentials
    with pytest.raises(SecureTransferError):
        decrypt_bundle(raw,"wrong")


def test_collect_and_restore_credentials_for_existing_import(tmp_path):
    source=Database(tmp_path/"source.db")
    target=Database(tmp_path/"target.db")
    try:
        site=source.add_site("Mallet")
        source_id=_add(source,site,"192.0.2.20","Hik DVR")
        source_store=MemoryCredentialStore(); source_store.data[source_id]="secret-20"
        owner=SimpleNamespace(
            db=source, credential_store=source_store,
            session_credentials={source_id:("admin","secret-20")},
        )
        payload=export_configuration(source)
        credentials,missing=collect_credentials(owner,payload)
        assert not missing
        assert len(credentials)==1

        import_configuration(target,payload)
        post=preview_configuration(target,payload)
        target_store=MemoryCredentialStore()
        target_owner=SimpleNamespace(db=target,credential_store=target_store,session_credentials={})
        result=restore_credentials(target_owner,payload,credentials,post)
        assert result["restored"]==1
        imported=target.list_devices(None)[0]
        imported_id=int(imported["id"])
        assert target_store.data[imported_id]=="secret-20"
        assert target_owner.session_credentials[imported_id]==("admin","secret-20")
        refreshed=target.get_device(imported_id)
        assert refreshed["credential_saved"]==1
        assert refreshed["credential_username"]=="admin"
    finally:
        source.close(); target.close()

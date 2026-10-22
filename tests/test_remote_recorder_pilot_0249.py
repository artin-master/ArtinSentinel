import json
from types import SimpleNamespace

import pytest

from artin_sentinel.db import Database
from artin_sentinel.device_intelligence import recorder_provider_hint
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.remote_access import (
    ACCESS_PRIVATE, access_label, validate_endpoint_url, validate_recorder_host,
    preserve_remote_inventory,
)


def test_remote_address_accepts_routed_ipv4_and_dns_but_rejects_urls_or_secrets():
    assert validate_recorder_host(" 10.20.30.40 ") == "10.20.30.40"
    assert validate_recorder_host("DVR.LOJA.INTERNO") == "dvr.loja.interno"
    for invalid in ("rtsp://host", "host:554", "user@host", "-danger", "", "2001:db8::1"):
        with pytest.raises(ValueError):
            validate_recorder_host(invalid)


def test_user_info_in_endpoint_is_rejected_before_database_write():
    assert validate_endpoint_url("rtsp://dvr.loja.interno:554/live", schemes=("rtsp",))
    with pytest.raises(ValueError):
        validate_endpoint_url("rtsp://admin:secret@dvr.loja.interno/live", schemes=("rtsp",))


def test_remote_site_metadata_survives_readonly_inventory_merge(tmp_path):
    db = Database(tmp_path / "pilot.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(site_id=site, ip="10.20.30.40", name="DVR loja",
                                  kind=DeviceKind.DVR, metadata={"connection_mode": ACCESS_PRIVATE}))
    db.upsert_device(Device(site_id=site, ip="10.20.30.40", name="DVR loja",
                            kind=DeviceKind.DVR, metadata={"discovery_sources": ["probe"]}))
    row = db.get_device(did)
    metadata = json.loads(row["metadata_json"])
    assert metadata["connection_mode"] == ACCESS_PRIVATE
    assert "remoto" in access_label(metadata)
    db.close()


def test_operator_selected_protocol_routes_generic_remote_recorder(tmp_path):
    db = Database(tmp_path / "routing.db")
    site = db.list_sites()[0]["id"]
    did = db.upsert_device(Device(site_id=site, ip="dvr.loja.interno", name="DVR loja",
                                  kind=DeviceKind.DVR, metadata={
                                      "connection_mode": ACCESS_PRIVATE, "recorder_protocol": "hikvision"}))
    assert recorder_provider_hint(db.get_device(did)) == "hikvision"
    db.merge_device_metadata(did, {"recorder_protocol": "intelbras"})
    assert recorder_provider_hint(db.get_device(did)) == "intelbras"
    db.close()


def test_transient_remote_outage_keeps_prior_channels_for_reconnection():
    old = [SimpleNamespace(available=True)]
    offline = [SimpleNamespace(available=False)]
    online = [SimpleNamespace(available=True)]
    assert preserve_remote_inventory(True, old, offline)
    assert preserve_remote_inventory(True, old, [])
    assert not preserve_remote_inventory(True, old, online)
    assert not preserve_remote_inventory(False, old, offline)

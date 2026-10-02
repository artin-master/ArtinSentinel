from pathlib import Path

from artin_akdb import (
    APPLICATION_DOMAINS,
    CORE_RECORDS,
    DomainExtension,
    SharedAkdbStore,
    build_bundle,
    record_by_legacy_key,
    validate_bundle,
)
from artin_sentinel import __version__
from artin_sentinel.akdb import public_summary, validate_shared_core_alignment
from artin_sentinel.akdb_shared import record_compatibility_candidate, sentinel_domain_extensions, sync_shared_akdb


def test_release_is_0215():
    assert __version__ == "0.2.94"


def test_shared_core_has_stable_ids_and_supported_apps():
    ids = [record.stable_id for record in CORE_RECORDS]
    assert len(ids) == len(set(ids))
    assert all(value.startswith("artin.device.") for value in ids)
    assert set(APPLICATION_DOMAINS) == {"sentinel", "netlens", "rescnow"}
    hik = record_by_legacy_key("hikvision-ds-7216hghi-f1")
    assert hik is not None
    assert hik.canonical_type == "dvr"
    assert "sentinel" in hik.domains
    assert "netlens" in hik.domains


def test_sentinel_extensions_cannot_diverge_from_shared_identity():
    assert validate_shared_core_alignment() == []
    rows = {row["key"]: row for row in public_summary()}
    row = rows["hikvision-ds-7216hghi-f1"]
    assert row["stable_id"] == "artin.device.hikvision-ds-7216hghi-f1"
    assert row["canonical_type"] == "dvr"
    assert row["revision"] >= 1
    assert "sentinel" in row["domains"]


def test_shared_store_syncs_core_and_domain_extension(tmp_path: Path):
    path = tmp_path / "akdb.sqlite3"
    with SharedAkdbStore(path) as store:
        changed = store.sync_catalog()
        assert changed == len(CORE_RECORDS)
        assert store.record_count() == len(CORE_RECORDS)
        ext = DomainExtension(
            stable_id="artin.device.hikvision-ds-7216hghi-f1",
            domain="sentinel",
            extension_schema="artin-akdb-sentinel-v1",
            payload={"provider": "hikvision", "stream_count": 2},
        )
        store.sync_extension(ext)
        # Re-sync is idempotent and does not create duplicate core records.
        assert store.sync_catalog() == 0
        assert store.record_count() == len(CORE_RECORDS)



def test_shared_store_never_downgrades_newer_record_revision(tmp_path: Path):
    path = tmp_path / "akdb.sqlite3"
    with SharedAkdbStore(path) as store:
        store.sync_catalog()
        stable_id = "artin.device.hikvision-ds-7216hghi-f1"
        row = store.conn.execute("SELECT payload_json FROM records WHERE stable_id=?", (stable_id,)).fetchone()
        import json
        payload = json.loads(row["payload_json"])
        payload["revision"] = 99
        store.conn.execute(
            "UPDATE records SET revision=99,payload_json=?,content_hash='newer' WHERE stable_id=?",
            (json.dumps(payload), stable_id),
        )
        store.conn.commit()
        store.sync_catalog()
        kept = store.conn.execute("SELECT revision FROM records WHERE stable_id=?", (stable_id,)).fetchone()
        assert kept["revision"] == 99


def test_bundle_roundtrip_contract_for_sentinel_netlens_rescnow():
    bundle = build_bundle(extensions=sentinel_domain_extensions())
    assert validate_bundle(bundle) == []
    domains = {row["domain"] for row in bundle["extensions"]}
    assert domains == {"sentinel"}
    assert bundle["applications"] == ["sentinel", "netlens", "rescnow"]


def test_field_report_enters_candidate_evidence_without_promoting_core(tmp_path: Path):
    path = tmp_path / "shared.sqlite3"
    report = {
        "device": {
            "display_name": "DVR da loja", "manufacturer": "Hikvision", "model": "DS-7216HGHI-F1",
            "firmware": "Vx", "kind": "dvr", "provider": "hikvision", "identity_confidence": 95,
        },
        "discovery": {
            "open_ports": [80, 554, 8000], "onvif_present": True, "web_present": True,
            "rtsp_present": True, "akdb_profile": "hikvision-ds-7216hghi-f1",
            "protocol_family": "hikvision-turbohd",
        },
        "summary": {"channels_saved": 16, "channels_available": 4, "audio_tracks": 1, "bidirectional_audio": 0},
    }
    result = record_compatibility_candidate(report, source_version="0.2.15", path=path)
    assert result["stable_id"] == "artin.device.hikvision-ds-7216hghi-f1"
    with SharedAkdbStore(path) as store:
        assert store.record_count() == len(CORE_RECORDS)
        assert store.evidence_count(app_id="artin-sentinel") == 1
        row = store.conn.execute("SELECT evidence_layer,status,payload_json FROM evidence").fetchone()
        assert row["evidence_layer"] == "field-test"
        assert row["status"] == "candidate"
        assert "DVR da loja" not in row["payload_json"]
        core = store.conn.execute(
            "SELECT validation_status FROM records WHERE stable_id=?",
            ("artin.device.hikvision-ds-7216hghi-f1",),
        ).fetchone()
        assert core["validation_status"] == "field-validated"


def test_sync_adapter_uses_configurable_shared_path(tmp_path: Path):
    status = sync_shared_akdb(tmp_path / "shared.sqlite3")
    assert status["records"] == len(CORE_RECORDS)
    assert status["path"].endswith("shared.sqlite3")


def test_ui_mentions_shared_akdb_architecture():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "Artin NetLens" in text
    assert "Artin RescNow" in text
    assert "AKDB ID" in text
    assert "Evidência candidata" in text

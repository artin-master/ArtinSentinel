import json
from pathlib import Path

from artin_akdb import CORE_REVISION, SCHEMA_VERSION, SharedAkdbStore, best_knowledge_match
from artin_sentinel import __version__
from artin_sentinel.compat_capture import build_discovery_homologation_report
from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind, DeviceStatus
from artin_sentinel.fingerprint import apply_device_fingerprint, identify_device


def test_release_version_0220(release_version):
    assert __version__ == release_version


def test_shared_matcher_recognizes_h2_platform_without_inventing_commercial_brand():
    match = best_knowledge_match({"model": "H2-52PGX", "text": "IPC H2-52PGX"}, minimum=70)
    assert match is not None
    assert match.stable_id == "artin.device.oem-h2-52pgx"
    assert match.record.canonical_type == "camera-fixed"
    assert match.record.subtype == "fixed/bullet"

    device = Device(
        name="IPC", ip="192.0.2.10", model="H2-52PGX", kind=DeviceKind.UNKNOWN,
        status=DeviceStatus.ONLINE, metadata={"open_ports": [80, 554], "evidence": ["IPC H2-52PGX"]},
    )
    decision = apply_device_fingerprint(device)
    assert decision.auto_applied is True
    assert device.kind == DeviceKind.CAMERA
    assert device.model == "H2-52PGX"
    # OEM platform knowledge must not falsely turn an unknown brand into Aitek.
    assert device.manufacturer == ""
    assert device.metadata["device_subtype"] == "fixed/bullet"
    assert "recorder-enumeration" in device.metadata["avoid_strategies"]


def test_hikvision_exact_model_returns_strategy_not_generic_camera_scan():
    device = Device(
        name="DS-7216HGHI-F1", ip="192.0.2.20", manufacturer="Hikvision",
        model="DS-7216HGHI-F1", kind=DeviceKind.UNKNOWN,
        metadata={"open_ports": [80, 554, 8000]},
    )
    decision = identify_device(device)
    assert decision.confidence >= 90
    assert decision.canonical_type == "dvr"
    assert "hikvision-recorder-rtsp" in decision.preferred_strategies
    assert "generic-camera-scan" in decision.avoid_strategies


def test_unknown_device_becomes_homologation_candidate():
    device = Device(name="Mystery", ip="192.0.2.30", model="ZX-NEW-999", metadata={"open_ports": [80, 554]})
    decision = apply_device_fingerprint(device)
    assert decision.stable_id == ""
    assert decision.candidate is True
    assert device.metadata["homologation_candidate"] is True
    assert device.metadata["homologation_status"] == "candidate"


def test_shared_akdb_sync_state_separates_official_revision_from_local_generation(tmp_path: Path):
    path = tmp_path / "shared.sqlite3"
    with SharedAkdbStore(path) as store:
        store.sync_catalog()
        state = store.sync_state(domain="sentinel")
        assert state["schema_version"] == SCHEMA_VERSION
        assert state["core_revision"] == CORE_REVISION
        assert state["local_generation"] == 0
        assert state["upload_pending"] is False
        store.record_evidence(
            app_id="artin-sentinel", evidence_layer="automatic-detection", status="candidate",
            payload={"model": "ZX-NEW-999"}, source_version="0.2.20",
        )
        state = store.sync_state(domain="sentinel")
        assert state["local_generation"] == 1
        assert state["upload_pending"] is True
        store.mark_uploaded()
        assert store.sync_state(domain="sentinel")["upload_pending"] is False


def test_known_device_is_found_by_mac_even_after_ip_change_and_archived_state_is_preserved(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site_id = int(db.list_sites()[0]["id"])
    existing = Device(
        site_id=site_id, name="X3-WE2Q", ip="192.168.15.47", mac="bc:ad:ae:2a:60:bf",
        manufacturer="IT-Blue", model="X3-WE2Q", kind=DeviceKind.CAMERA,
    )
    device_id = db.upsert_device(existing)
    db.archive_device(device_id, True)

    rediscovered = Device(
        site_id=site_id, name="Web Viewer", ip="192.168.15.46", mac="bc:ad:ae:2a:60:bf",
        kind=DeviceKind.CAMERA, status=DeviceStatus.ONLINE,
    )
    known = db.find_known_for_discovery(site_id, rediscovered)
    assert known is not None and int(known["id"]) == device_id
    db.upsert_device(rediscovered)
    assert int(db.get_device(device_id)["archived"]) == 1
    assert {ep["ip"] for ep in db.list_device_endpoints(device_id)} == {"192.168.15.46", "192.168.15.47"}

    db.delete_device_permanently(device_id)
    assert db.find_known_for_discovery(site_id, rediscovered) is None
    db.close()


def test_discovery_homologation_report_is_sanitized_and_reviewable():
    device = Device(
        name="New bullet", ip="192.168.15.188", mac="aa:bb:cc:dd:ee:ff",
        model="H2-52PGX", kind=DeviceKind.CAMERA, status=DeviceStatus.ONLINE,
        web_url="http://192.168.15.188/", rtsp_url="rtsp://192.168.15.188:554/",
        metadata={"open_ports": [80, 554], "evidence": ["modelo/plataforma H2-52PGX"]},
    )
    apply_device_fingerprint(device)
    report = build_discovery_homologation_report(device, sentinel_version="0.2.20")
    raw = json.dumps(report)
    assert report["schema"] == "artin-akdb-field-report-v1"
    assert report["review_state"] == "candidate"
    assert "192.168.15.188" not in raw
    assert "aa:bb:cc:dd:ee:ff" not in raw
    assert report["identity"]["canonical_type"] == "camera-fixed"


def test_discovery_ui_marks_known_devices_as_included_and_offers_akdb_report():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "find_known_for_discovery" in source
    assert "já cadastrados reconhecidos e marcados como incluídos" in source
    assert '"* Incluído"' in source
    assert 'QPushButton("Relatório AKDB")' in source
    assert "Nenhum novo equipamento" in source


def test_akdb_backfill_corrects_stale_generic_type_but_preserves_manual_override(tmp_path: Path):
    db = Database(tmp_path / "backfill.db")
    site_id = int(db.list_sites()[0]["id"])
    auto_id = db.upsert_device(Device(site_id=site_id, name="IPC", ip="192.0.2.41", model="H2-52PGX", kind=DeviceKind.NVR))
    manual_id = db.upsert_device(Device(site_id=site_id, name="Manual", ip="192.0.2.42", model="H2-52PGX", kind=DeviceKind.NVR))
    db.update_device_identity(manual_id, "Manual", "nvr", "", "H2-52PGX")
    # Simulate stale pre-0.2.20 rows so migration/backfill has work to do.
    db.conn.execute("UPDATE devices SET akdb_stable_id='',canonical_type='unknown',device_subtype='',fingerprint_confidence=0 WHERE id IN (?,?)", (auto_id, manual_id))
    db.conn.commit()
    db._migrate_0220()
    auto = db.get_device(auto_id)
    manual = db.get_device(manual_id)
    assert auto["kind"] == "camera"
    assert auto["akdb_stable_id"] == "artin.device.oem-h2-52pgx"
    assert manual["kind"] == "nvr"  # explicit operator decision still wins operationally
    assert manual["akdb_stable_id"] == "artin.device.oem-h2-52pgx"
    db.close()


def test_field_report_registration_advances_local_generation_without_touching_core(tmp_path: Path):
    from artin_akdb import build_field_report
    path = tmp_path / "reports.sqlite3"
    report = build_field_report(
        source_app="artin-sentinel", source_version="0.2.20",
        identity={"stable_id": "", "canonical_type": "camera-fixed", "confidence": 60},
        evidence={"model": "ZX-NEW-999"}, domain_data={"domain": "sentinel"},
    )
    with SharedAkdbStore(path) as store:
        store.sync_catalog()
        before = store.sync_state(domain="sentinel")
        report_id = store.register_field_report(app_id="artin-sentinel", report=report)
        after = store.sync_state(domain="sentinel")
        assert report_id > 0
        assert store.field_report_count(app_id="artin-sentinel") == 1
        assert after["local_generation"] == before["local_generation"] + 1
        assert after["core_revision"] == before["core_revision"]
        assert after["upload_pending"] is True

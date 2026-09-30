import hashlib
import json
from pathlib import Path

from artin_akdb import CORE_REVISION, SharedAkdbStore, build_bundle
from artin_sentinel import __version__
from artin_sentinel.akdb_shared import sentinel_domain_extensions
from artin_sentinel.akdb_sync import (
    AkdbSyncSettings,
    apply_official_update,
    sanitize_for_submission,
    submit_pending,
    pending_proposals,
)


def test_release_0243():
    assert __version__ == "0.2.90"


def test_field_report_is_queued_without_promoting_core(tmp_path: Path):
    path = tmp_path / "akdb.sqlite3"
    report = {
        "schema": "artin-akdb-field-report-v1",
        "review_state": "candidate",
        "source": {"app": "artin-sentinel", "version": "0.2.43"},
        "identity": {"manufacturer": "Intelbras", "model": "NVD 1516"},
        "evidence": {"onvif": True},
    }
    with SharedAkdbStore(path) as store:
        store.sync_catalog()
        before = store.record_count()
        report_id = store.register_field_report(app_id="artin-sentinel", report=report)
        assert report_id > 0
        assert store.record_count() == before
        assert store.pending_submission_count() == 1
        queued = store.pending_submissions()
        assert queued[0]["report"]["identity"]["model"] == "NVD 1516"


def test_submission_sanitizer_removes_installation_identifiers():
    report = {
        "identity": {
            "manufacturer": "Intelbras",
            "model": "NVD 1516",
            "ip": "192.168.15.250",
            "mac": "AA:BB:CC:DD:EE:FF",
            "serial": "ABC123",
        },
        "evidence": {
            "detail": "rtsp://admin:secret@192.168.15.250/cam/realmonitor",
            "ports": [80, 554, 37777],
        },
    }
    sanitized = sanitize_for_submission(report)
    raw = json.dumps(sanitized)
    assert "192.168.15.250" not in raw
    assert "AA:BB:CC:DD:EE:FF" not in raw
    assert "ABC123" not in raw
    assert "admin:secret" not in raw
    assert "NVD 1516" in raw
    assert "37777" in raw


def test_official_bundle_apply_preserves_pending_local_candidates(tmp_path: Path):
    path = tmp_path / "akdb.sqlite3"
    bundle = build_bundle(extensions=sentinel_domain_extensions())
    raw = (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    report = {
        "schema": "artin-akdb-field-report-v1",
        "review_state": "candidate",
        "source": {"app": "artin-sentinel", "version": "0.2.43"},
        "identity": {"manufacturer": "Intelbras", "model": "NVD 1516"},
        "evidence": {"onvif": True},
    }
    with SharedAkdbStore(path) as store:
        store.sync_catalog()
        store.register_field_report(app_id="artin-sentinel", report=report)
        assert store.pending_submission_count() == 1
    result = apply_official_update(
        {
            "manifest": {"release_revision": 1},
            "bundle": bundle,
            "bundle_sha256": digest,
        },
        store_path=path,
    )
    assert result["release_revision"] == 1
    with SharedAkdbStore(path) as store:
        assert store.pending_submission_count() == 1
        assert store.field_report_count(app_id="artin-sentinel") == 1


def test_submit_pending_uses_queue_state_without_network(monkeypatch, tmp_path: Path):
    path = tmp_path / "akdb.sqlite3"
    report = {
        "schema": "artin-akdb-field-report-v1",
        "review_state": "candidate",
        "source": {"app": "artin-sentinel", "version": "0.2.43"},
        "identity": {"manufacturer": "Intelbras", "model": "NVD 1516"},
        "evidence": {"rtsp": True},
    }
    with SharedAkdbStore(path) as store:
        store.register_field_report(app_id="artin-sentinel", report=report)

    import artin_sentinel.akdb_sync as sync
    monkeypatch.setattr(sync, "submit_report_to_github", lambda **kwargs: "https://github.example/inbox/candidate.json")
    result = submit_pending(
        store_path=path,
        settings=AkdbSyncSettings(github_repo="artin-master/ArtinUpdates"),
        token="test-token",
        reviewed={item["report_id"]: item["review_sha256"] for item in pending_proposals(store_path=path)},
    )
    assert len(result["submitted"]) == 1
    assert result["failed"] == []
    with SharedAkdbStore(path) as store:
        assert store.pending_submission_count() == 0


def test_app_exposes_akdb_sync_controls():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "AKDB Sync + Field Learning" in text
    assert "Verificar AKDB" in text
    assert "Atualizar base" in text
    assert "Revisar candidatos" in text
    assert "Configurar token GitHub" in text


def test_equal_knowledge_release_establishes_baseline_without_prompt(tmp_path: Path):
    from artin_sentinel.akdb_sync import check_official_update
    bundle = build_bundle(extensions=sentinel_domain_extensions())
    bundle_path = tmp_path / "bundle.json"
    raw = (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode()
    bundle_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    manifest_path = tmp_path / "stable.json"
    manifest_path.write_text(json.dumps({
        "schema": "artin-akdb-manifest-v1",
        "channel": "stable",
        "release_revision": 1,
        "core_version": "0.2.0",
        "core_revision": CORE_REVISION,
        "bundle": {"url": bundle_path.resolve().as_uri(), "sha256": digest, "size": len(raw)},
    }), encoding="utf-8")
    db = tmp_path / "akdb.sqlite3"
    with SharedAkdbStore(db) as store:
        store.sync_catalog()
        for ext in sentinel_domain_extensions():
            store.sync_extension(ext)
    result = check_official_update(store_path=db, manifest_url=manifest_path.resolve().as_uri())
    assert result["available"] is False
    with SharedAkdbStore(db) as store:
        assert store.official_release_state()["release_revision"] == 1

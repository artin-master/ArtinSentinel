import json

import pytest

from artin_akdb import SharedAkdbStore
from artin_sentinel.akdb_sync import (
    AkdbSyncSettings, export_proposals, load_settings,
    pending_proposals, submit_pending,
)


def test_review_sanitizes_candidate_and_compares_official_identity(tmp_path):
    db = tmp_path / "akdb.sqlite3"
    with SharedAkdbStore(db) as store:
        store.sync_catalog()
        row = store.conn.execute("SELECT stable_id,manufacturer,model FROM records WHERE model!='' LIMIT 1").fetchone()
        assert row is not None
        store.register_field_report(app_id="artin-sentinel", report={
            "schema": "artin-akdb-field-report-v1", "review_state": "candidate",
            "source": {"app": "artin-sentinel"},
            "identity": {"observed_manufacturer": row["manufacturer"], "observed_model": row["model"],
                         "serial": "SN-PRIVATE", "hostname": "site-interno"},
            "evidence": {"observation": "rtsp://admin:1234@192.168.15.1/live password=secret contact tech@example.org",
                         "ipv6": "2001:db8::1234", "ports": [554]},
        })
    proposal = pending_proposals(store_path=db)[0]
    assert proposal["comparison"] == "identidade existente"
    assert proposal["official"][0]["stable_id"] == row["stable_id"]
    raw = json.dumps(proposal["report"])
    for secret in ("SN-PRIVATE", "site-interno", "admin:1234", "192.168.15.1", "password=secret", "tech@example.org", "2001:db8::1234"):
        assert secret not in raw
    out = export_proposals(tmp_path / "proposal.json", [proposal])
    content = json.loads(out.read_text())
    assert content["schema"] == "artin-akdb-contribution-v1"
    assert content["candidates"][0]["report"] == proposal["report"]
    with SharedAkdbStore(db) as store:
        assert store.pending_submission_count() == 1
    with pytest.raises(FileExistsError):
        export_proposals(out, [proposal])


def test_explicit_review_is_required_and_only_selected_report_is_submitted(monkeypatch, tmp_path):
    db = tmp_path / "akdb.sqlite3"
    with SharedAkdbStore(db) as store:
        for model in ("Unlisted 1", "Unlisted 2"):
            store.register_field_report(app_id="artin-sentinel", report={
                "schema": "artin-akdb-field-report-v1", "source": {"app": "artin-sentinel"},
                "identity": {"manufacturer": "Test", "model": model},
            })
    items = pending_proposals(store_path=db)
    assert all(item["comparison"] == "nova identidade" for item in items)
    calls = []
    import artin_sentinel.akdb_sync as sync
    monkeypatch.setattr(sync, "submit_report_to_github", lambda **kwargs: calls.append(kwargs) or "https://example.test/proposal")
    with pytest.raises(ValueError, match="Revise"):
        submit_pending(store_path=db, token="fake", settings=AkdbSyncSettings())
    with pytest.raises(ValueError, match="mudou"):
        submit_pending(store_path=db, token="fake", settings=AkdbSyncSettings(),
                       reviewed={items[0]["report_id"]: "wrong"}, limit=1)
    assert not calls
    result = submit_pending(store_path=db, token="fake", settings=AkdbSyncSettings(),
                            reviewed={items[1]["report_id"]: items[1]["review_sha256"]}, limit=1)
    assert [row["report_id"] for row in result["submitted"]] == [items[1]["report_id"]]
    assert calls[0]["report_id"] == items[1]["report_id"]
    with SharedAkdbStore(db) as store:
        assert store.pending_submission_count() == 1


def test_old_auto_submit_setting_is_disabled_on_load(tmp_path):
    (tmp_path / "akdb-sync-settings.json").write_text(json.dumps({"auto_submit": True}))
    assert load_settings(tmp_path).auto_submit is False

import json
import sqlite3

import pytest

import artin_sentinel.db as db_module
from artin_sentinel.db import Database
from artin_sentinel.domain import Device


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "web.db")
    try:
        yield database
    finally:
        database.close()


def add_endpoint(db, ip="192.0.2.10", **kwargs):
    site_id = db.list_sites()[0]["id"]
    device_id = db.upsert_device(Device(site_id=site_id, ip=ip, name="Device", **kwargs))
    return device_id, db.get_device_endpoint(device_id, ip)["id"]


def record(db, endpoint_id, **kwargs):
    values = dict(ip="192.0.2.10", scheme="https", port=443, confirmed=True,
                  http_status=200, tls_status="unverified")
    values.update(kwargs)
    return db.record_web_service_check(endpoint_id, **values)


def snapshot(db):
    return {
        table: [dict(row) for row in db.conn.execute(f"SELECT * FROM {table} ORDER BY id")]
        for table in ("device_web_services", "device_web_service_checks")
    }


def test_new_database_creates_schema_without_enabling_foreign_keys(db):
    assert snapshot(db) == {"device_web_services": [], "device_web_service_checks": []}
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    assert db.conn.execute("PRAGMA foreign_key_list(device_web_services)").fetchone()["table"] == "device_endpoints"
    assert db.conn.execute("PRAGMA foreign_key_list(device_web_service_checks)").fetchone()["table"] == "device_web_services"
    assert db.conn.execute(
        "SELECT name FROM sqlite_master WHERE name='idx_web_service_checks_history'"
    ).fetchone()
    for table in snapshot(db):
        columns = db._column_names(table)
        assert not columns.intersection({"url", "web_url", "username", "password", "headers", "body"})


def test_migration_is_idempotent_and_preserves_history(db):
    _device, endpoint = add_endpoint(db)
    record(db, endpoint)
    before = snapshot(db)
    db._migrate_web_services()
    db._migrate_web_services()
    assert snapshot(db) == before


def test_existing_database_preserves_legacy_data_without_backfill(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with monkeypatch.context() as patch:
        patch.setattr(Database, "_migrate_web_services", lambda self: None)
        legacy = Database(path)
        device, endpoint = add_endpoint(
            legacy, web_url="https://192.0.2.10:8443/config?legacy=1",
            metadata={"open_ports": [80, 443, 8443], "evidence": ["legacy"]},
        )
        original_device = dict(legacy.get_device(device))
        original_endpoint = dict(legacy.get_device_endpoint(device, "192.0.2.10"))
    # Isolate this additive migration: older startup migrations already refresh
    # identity metadata and timestamps when an existing database is reopened.
    upgraded = legacy
    try:
        upgraded._migrate_web_services()
        assert dict(upgraded.get_device(device)) == original_device
        ep = upgraded.get_device_endpoint(device, "192.0.2.10")
        for key in ("id", "ip", "web_url", "services_json"):
            assert ep[key] == original_endpoint[key]
        assert snapshot(upgraded) == {"device_web_services": [], "device_web_service_checks": []}
        assert upgraded.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    finally:
        upgraded.close()
    reopened = Database(path)
    try:
        assert reopened.get_device(device)["web_url"] == original_device["web_url"]
        assert snapshot(reopened) == {"device_web_services": [], "device_web_service_checks": []}
    finally:
        reopened.close()


def test_multiple_services_and_unique_endpoint_scheme_port(db):
    device, endpoint = add_endpoint(db)
    https = record(db, endpoint)
    assert record(db, endpoint) == https
    record(db, endpoint, port=8443)
    record(db, endpoint, scheme="http", port=80, tls_status="not_applicable")
    rows = db.list_device_web_services(device)
    assert {(row["scheme"], row["port"]) for row in rows} == {("http", 80), ("https", 443), ("https", 8443)}
    assert len(db.list_web_service_checks(https)) == 2
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute("""
            INSERT INTO device_web_services (
                endpoint_id,scheme,port,first_checked_at,last_checked_at,
                last_outcome,last_tls_status
            ) SELECT endpoint_id,scheme,port,first_checked_at,last_checked_at,
                     last_outcome,last_tls_status FROM device_web_services WHERE id=?
        """, (https,))
    db.conn.rollback()


def test_success_failure_recovery_preserves_confirmation_and_history(db, monkeypatch):
    device, endpoint = add_endpoint(db)
    times = iter(f"2026-10-01T12:00:0{i}+00:00" for i in range(4))
    monkeypatch.setattr(db_module, "utcnow", lambda: next(times))
    service = record(db, endpoint, tls_status="verified")
    original = dict(db.list_device_web_services(device)[0])
    for expected_failures in (1, 2):
        record(db, endpoint, confirmed=False, http_status=None, error_code="timeout")
        failed = db.list_device_web_services(device)[0]
        assert failed["first_confirmed_at"] == original["first_confirmed_at"]
        assert failed["last_confirmed_at"] == original["last_confirmed_at"]
        assert failed["consecutive_failures"] == expected_failures
        assert failed["last_outcome"] == "failed"
    last_failure = failed["last_failed_at"]
    record(db, endpoint, http_status=401)
    recovered = db.list_device_web_services(device)[0]
    assert recovered["first_confirmed_at"] == original["first_confirmed_at"]
    assert recovered["first_checked_at"] == original["first_checked_at"]
    assert recovered["last_confirmed_at"] == "2026-10-01T12:00:03+00:00"
    assert recovered["last_failed_at"] == last_failure
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_error_code"] == ""
    assert recovered["last_http_status"] == 401
    history = db.list_web_service_checks(service)
    assert [row["outcome"] for row in history] == ["confirmed", "failed", "failed", "confirmed"]
    assert history[-1]["tls_status"] == "verified"
    assert len(db.list_web_service_checks(service, limit=2)) == 2


def test_failure_without_previous_confirmation_is_not_listed_as_confirmed(db):
    device, endpoint = add_endpoint(db)
    record(db, endpoint, confirmed=False, http_status=None, error_code="connection_error")
    assert db.list_device_web_services(device) == []
    row = db.list_device_web_services(device, confirmed_only=False)[0]
    assert row["first_confirmed_at"] is None
    assert row["last_confirmed_at"] is None
    assert row["consecutive_failures"] == 1


@pytest.mark.parametrize("existing", [False, True])
def test_history_insert_failure_rolls_back_service_state(db, existing):
    _device, endpoint = add_endpoint(db)
    if existing:
        record(db, endpoint)
    before = snapshot(db)
    db.conn.execute("""
        CREATE TRIGGER reject_web_history BEFORE INSERT ON device_web_service_checks
        BEGIN SELECT RAISE(ABORT, 'history rejected'); END
    """)
    db.conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="history rejected"):
        record(db, endpoint, confirmed=False, http_status=None, error_code="timeout")
    assert snapshot(db) == before
    assert not db.conn.in_transaction


def test_equipment_isolation_and_deletion_preserve_other_equipment(db):
    first, ep1 = add_endpoint(db)
    second, ep2 = add_endpoint(db, ip="192.0.2.11")
    first_service = record(db, ep1)
    second_service = record(db, ep2, ip="192.0.2.11")
    assert [row["id"] for row in db.list_device_web_services(first)] == [first_service]
    assert [row["id"] for row in db.list_device_web_services(second)] == [second_service]
    other_before = dict(db.list_device_web_services(second)[0])
    other_history = [dict(row) for row in db.list_web_service_checks(second_service)]
    db.delete_device_permanently(first)
    assert db.get_device(first) is None
    assert db.list_device_web_services(first) == []
    assert db.list_web_service_checks(first_service) == []
    assert dict(db.list_device_web_services(second)[0]) == other_before
    assert [dict(row) for row in db.list_web_service_checks(second_service)] == other_history
    assert db.conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_delete_correlated_group_removes_secondary_seed_endpoint_services(db):
    first, ep1 = add_endpoint(db)
    second, ep2 = add_endpoint(db, ip="192.0.2.11")
    services = [record(db, ep1), record(db, ep2, ip="192.0.2.11")]
    db.conn.execute("UPDATE devices SET correlated_to=? WHERE id=?", (first, second))
    db.conn.commit()
    assert db.get_device_endpoint(second, "192.0.2.10")["id"] == ep1
    assert {row["id"] for row in db.list_device_web_services(first)} == set(services)
    assert {row["id"] for row in db.list_device_web_services(second)} == set(services)
    db.delete_device_permanently(second)
    assert db.get_device(first) is None
    assert db.get_device(second) is None
    assert all(db.list_web_service_checks(service) == [] for service in services)
    assert snapshot(db) == {"device_web_services": [], "device_web_service_checks": []}


@pytest.mark.parametrize("ip,metadata,transient", [
    ("127.0.0.1", {}, False),
    ("127.20.30.40", {}, False),
    ("::1", {}, False),
    ("::ffff:127.0.0.1", {}, False),
    ("192.0.2.10", {"connection_mode": "site_connector"}, False),
    ("192.0.2.10", {}, True),
    ("localhost", {}, False),
])
def test_loopback_tunnel_and_transient_results_are_not_persisted(db, ip, metadata, transient):
    _device, endpoint = add_endpoint(db, ip=ip, metadata=metadata)
    with pytest.raises(ValueError):
        record(db, endpoint, ip=ip, transient=transient)
    assert snapshot(db) == {"device_web_services": [], "device_web_service_checks": []}


@pytest.mark.parametrize("patch", [
    {"ip": "192.0.2.11"},
    {"scheme": "rtsp"},
    {"port": 0},
    {"port": 65536},
    {"port": True},
    {"confirmed": "yes"},
    {"http_status": None},
    {"http_status": 99},
    {"tls_status": "trusted"},
    {"scheme": "http", "tls_status": "verified"},
    {"latency_ms": float("nan")},
    {"latency_ms": float("inf")},
    {"latency_ms": -1},
])
def test_invalid_structured_results_do_not_write(db, patch):
    _device, endpoint = add_endpoint(db)
    with pytest.raises(ValueError):
        record(db, endpoint, **patch)
    assert snapshot(db) == {"device_web_services": [], "device_web_service_checks": []}


def test_unknown_errors_are_sanitized_and_no_response_text_is_stored(db):
    device, endpoint = add_endpoint(db)
    secret = "http://user:password@192.0.2.10/?token=secret Authorization: Bearer secret"
    service = record(db, endpoint, confirmed=False, http_status=None, error_code=secret, latency_ms=12.5)
    assert db.list_device_web_services(device, confirmed_only=False)[0]["last_error_code"] == "other_error"
    assert db.list_web_service_checks(service)[0]["error_code"] == "other_error"
    assert "password" not in json.dumps(snapshot(db))
    assert "Bearer" not in json.dumps(snapshot(db))


def test_missing_endpoint_and_history_limit_validation(db):
    assert db.get_device_endpoint(9999, "192.0.2.10") is None
    assert db.list_device_web_services(9999) == []
    with pytest.raises(ValueError, match="inexistente"):
        record(db, 9999)
    for limit in (0, -1, True):
        with pytest.raises(ValueError):
            db.list_web_service_checks(1, limit=limit)


def test_same_ip_in_different_sites_has_independent_confirmation(db):
    first, ep1 = add_endpoint(db)
    other_site = db.add_site("Other Site")
    second = db.upsert_device(Device(site_id=other_site, ip="192.0.2.10", name="Other Device"))
    ep2 = db.get_device_endpoint(second, "192.0.2.10")["id"]
    first_service = record(db, ep1)
    second_service = record(db, ep2)
    assert [row["id"] for row in db.list_device_web_services(first)] == [first_service]
    assert [row["id"] for row in db.list_device_web_services(second)] == [second_service]


def test_history_survives_database_reopen(tmp_path):
    path = tmp_path / "reopen.db"
    database = Database(path)
    try:
        device, endpoint = add_endpoint(database)
        record(database, endpoint)
        before = snapshot(database)
    finally:
        database.close()
    reopened = Database(path)
    try:
        assert snapshot(reopened) == before
        assert len(reopened.list_device_web_services(device)) == 1
    finally:
        reopened.close()

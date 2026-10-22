from pathlib import Path

import artin_sentinel.services as services
from artin_sentinel import __version__
from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind, DeviceStatus


def _itblue(site_id: int, ip: str, *, name: str, model: str, web: str = "", rtsp: str = "") -> Device:
    return Device(
        site_id=site_id,
        name=name,
        ip=ip,
        mac="bc:ad:ae:2a:60:bf",
        manufacturer="IT-Blue",
        model=model,
        kind=DeviceKind.CAMERA,
        status=DeviceStatus.ONLINE,
        web_url=web,
        rtsp_url=rtsp,
    )


def test_release_version_0219(release_version):
    assert __version__ == release_version


def test_same_site_same_mac_becomes_one_physical_device_with_two_endpoints(tmp_path: Path):
    db = Database(tmp_path / "multi.db")
    site_id = int(db.list_sites()[0]["id"])

    primary_id = db.upsert_device(
        _itblue(
            site_id, "192.168.15.47", name="X3-WE2Q", model="X3-WE2Q",
            rtsp="rtsp://192.168.15.47:554/",
        )
    )
    second_id = db.upsert_device(
        _itblue(
            site_id, "192.168.15.46", name="Web Viewer", model="Web Viewer",
            web="http://192.168.15.46/",
        )
    )

    assert second_id == primary_id
    devices = db.list_devices(site_id)
    assert len(devices) == 1
    assert devices[0]["ip"] == "192.168.15.47"
    # A generic secondary endpoint must not downgrade a confirmed model.
    assert devices[0]["model"] == "X3-WE2Q"
    assert devices[0]["name"] == "X3-WE2Q"

    endpoints = db.list_device_endpoints(primary_id)
    assert {row["ip"] for row in endpoints} == {"192.168.15.46", "192.168.15.47"}
    assert next(row for row in endpoints if row["ip"] == "192.168.15.46")["web_url"] == "http://192.168.15.46/"
    assert next(row for row in endpoints if row["ip"] == "192.168.15.47")["rtsp_url"] == "rtsp://192.168.15.47:554/"
    db.close()


def test_preexisting_duplicate_rows_are_linked_not_deleted_on_reopen(tmp_path: Path):
    path = tmp_path / "legacy.db"
    db = Database(path)
    site_id = int(db.list_sites()[0]["id"])
    first = db.upsert_device(Device(site_id=site_id, name="X3-WE2Q", ip="192.168.15.47"))
    second = db.upsert_device(Device(site_id=site_id, name="Web Viewer", ip="192.168.15.46"))
    assert first != second
    db.conn.execute(
        "UPDATE devices SET mac=? WHERE id IN (?,?)",
        ("bc:ad:ae:2a:60:bf", first, second),
    )
    db.conn.commit()
    db.close()

    reopened = Database(path)
    visible = reopened.list_devices(site_id)
    assert len(visible) == 1
    canonical = int(visible[0]["id"])
    hidden = reopened.conn.execute(
        "SELECT * FROM devices WHERE id<>? AND site_id=?", (canonical, site_id)
    ).fetchone()
    assert hidden is not None
    assert int(hidden["correlated_to"]) == canonical
    assert reopened.conn.execute("SELECT COUNT(*) c FROM devices WHERE site_id=?", (site_id,)).fetchone()["c"] == 2
    assert {row["ip"] for row in reopened.list_device_endpoints(canonical)} == {"192.168.15.46", "192.168.15.47"}
    reopened.close()


def test_multi_endpoint_monitor_is_online_when_any_endpoint_answers(monkeypatch):
    def fake_diagnose(ip, web_url="", rtsp_url=""):
        online = ip.endswith(".47")
        return services.DiagnosticSummary(
            online=online,
            ping_ok=online,
            latency_ms=1.5 if online else None,
            open_ports=[554] if online else [],
            web_ok=True if web_url and online else None,
            rtsp_ok=True if rtsp_url and online else None,
            details=[ip],
        )

    monkeypatch.setattr(services, "diagnose", fake_diagnose)
    result = services.diagnose_endpoints([
        {"ip": "192.168.15.46", "web_url": "http://192.168.15.46/", "rtsp_url": ""},
        {"ip": "192.168.15.47", "web_url": "", "rtsp_url": "rtsp://192.168.15.47:554/"},
    ])
    assert result.online is True
    assert result.active_ip == "192.168.15.47"
    assert result.endpoint_statuses == {
        "192.168.15.46": "offline",
        "192.168.15.47": "online",
    }


def test_live_source_tree_contains_status_icons_and_endpoint_tooltips():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "def status_dot_icon" in source
    assert "device_item.setIcon(0, status_dot_icon(state))" in source
    assert 'site_state = "online"' in source
    assert "MAC:" in source
    assert "list_device_endpoints" in source
    assert "Endpoints do mesmo equipamento" in source

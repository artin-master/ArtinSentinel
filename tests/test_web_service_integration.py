from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QMainWindow, QMenu, QPushButton, QTableWidgetItem, QTabWidget

from artin_sentinel import services
from artin_sentinel.app import MainWindow
import artin_sentinel.app as app_module
from artin_sentinel.db import Database
from artin_sentinel.domain import Device
from artin_sentinel.lan_discovery import HostObservation
from artin_sentinel.web_services import (
    WebProbeResult, ordered_web_services, web_service_candidates, web_services_from_checks,
)


def check(ip="192.0.2.10", scheme="http", port=80, confirmed=True, *, at="2026-10-01T12:00:00+00:00"):
    return WebProbeResult(ip, scheme, port, at, confirmed, 200 if confirmed else None,
                          "verified" if scheme == "https" else "not_applicable",
                          "" if confirmed else "connection_error", 1.0)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "integration.db")
    try:
        yield database
    finally:
        database.close()


def device(db, ip="192.0.2.10", **kwargs):
    return Device(site_id=db.list_sites()[0]["id"], name="Camera", ip=ip, **kwargs)


def persist(db, device_id, found, checks):
    services.persist_discovered_web_checks(db, device_id, found, checks)


def test_default_candidates_are_independent_of_open_tcp_ports():
    assert web_service_candidates("192.0.2.10") == [
        ("http", 80), ("https", 443), ("http", 8080), ("https", 8443),
    ]


@pytest.mark.parametrize("hint,extra", [
    ("https://192.0.2.10:9443/config?token=secret#anchor", [("https", 9443)]),
    ("http://192.0.2.10:8081/login", [("http", 8081)]),
    ("http://192.0.2.10:443/login", [("http", 443)]),
    ("http://192.0.2.10/", []),
    ("https://user:secret@192.0.2.10:9443/", []),
    ("https://user@192.0.2.10:9443/", []),
    ("https://192.0.2.11:9443/", []),
    ("https://camera.local:9443/", []),
    ("https://192.0.2.10:0/", []),
    ("https://192.0.2.10:65536/", []),
    ("https://192.0.2.10:bad/", []),
    ("rtsp://192.0.2.10:554/", []),
])
def test_only_safe_hints_add_a_candidate(hint, extra):
    assert web_service_candidates("192.0.2.10", hint) == web_service_candidates("192.0.2.10") + extra


def test_ipv6_hint_matches_normalized_endpoint():
    assert ("https", 9443) in web_service_candidates("2001:db8::1", "https://[2001:db8:0:0::1]:9443/path")


def test_probe_uses_safe_additional_candidates_without_promoting_them(monkeypatch, db):
    found = device(db, web_url="https://192.0.2.10:9443/path?token=secret")
    probe = Mock(side_effect=lambda ip, scheme, port: check(ip, scheme, port, False))
    monkeypatch.setattr(services, "probe_web_service", probe)
    results = services.probe_discovered_web_services(found, [("http", 9080)])
    assert probe.call_count == 6
    assert probe.call_args_list[-2].args == (found.ip, "https", 9443)
    assert probe.call_args_list[-1].args == (found.ip, "http", 9080)
    assert not any(result.confirmed for result in results)


@pytest.mark.parametrize("confirmed", [True, False])
def test_discovery_probes_without_changing_classification_or_registering(monkeypatch, db, confirmed):
    observation = HostObservation("192.0.2.10", open_ports=[80, 443, 554], rtsp_url="rtsp://192.0.2.10/")
    other = HostObservation("192.0.2.11", open_ports=[80])
    monkeypatch.setattr(services, "scan_local_cctv", lambda **kw: ([], [observation, other], 2))
    monkeypatch.setattr(services, "discover_onvif_devices", lambda site: [])
    monkeypatch.setattr(services, "apply_device_fingerprint", lambda found: None)
    probe = Mock(side_effect=lambda ip, scheme, port: check(ip, scheme, port, confirmed))
    monkeypatch.setattr(services, "probe_web_service", probe)
    report = services.discover_network_devices(db.list_sites()[0]["id"])
    assert [found.ip for found in report.devices] == [observation.ip]
    assert len(report.other_hosts) == 1
    assert probe.call_count == 4
    assert {item.scheme for item in report.web_results[observation.ip]} == {"http", "https"}
    assert all(item.confirmed == confirmed for item in report.web_results[observation.ip])
    assert db.list_devices() == []
    assert db.conn.execute("SELECT count(*) FROM device_web_services").fetchone()[0] == 0


def test_known_device_records_each_service_on_correct_secondary_endpoint(db):
    primary = device(db)
    owner = db.upsert_device(primary)
    secondary = device(db, "192.0.2.20")
    db.register_device_endpoint(owner, ip=secondary.ip)
    checks = [check(secondary.ip), check(secondary.ip, "https", 443), check(secondary.ip, "http", 8080)]
    persist(db, owner, secondary, checks)
    rows = db.list_device_web_services(owner)
    assert len(rows) == 3
    assert {row["endpoint_id"] for row in rows} == {db.get_device_endpoint(owner, secondary.ip)["id"]}
    assert {row["endpoint_ip"] for row in rows} == {secondary.ip}
    assert db.get_device(owner)["web_url"] == ""


def test_failure_preserves_historical_confirmation_and_recovery(db):
    found = device(db)
    owner = db.upsert_device(found)
    for success in (True, False):
        persist(db, owner, found, [check(confirmed=success)])
    row = db.list_device_web_services(owner)[0]
    assert row["last_outcome"] == "failed"
    assert row["last_confirmed_at"]
    assert row["consecutive_failures"] == 1
    persist(db, owner, found, [check()])
    row = db.list_device_web_services(owner)[0]
    assert row["last_outcome"] == "confirmed"
    assert row["consecutive_failures"] == 0
    assert db.conn.execute("SELECT count(*) FROM device_web_service_checks").fetchone()[0] == 3


@pytest.mark.parametrize("ip,metadata", [
    ("127.0.0.1", {}), ("::1", {}), ("::ffff:127.0.0.1", {}),
    ("192.0.2.10", {"connection_mode": "site_connector"}),
    ("192.0.2.10", {"transient": True}),
])
def test_loopback_and_tunnel_checks_never_persist(db, ip, metadata):
    found = device(db, ip, metadata=metadata)
    owner = db.upsert_device(found)
    persist(db, owner, found, [check(ip)])
    assert db.list_device_web_services(owner, confirmed_only=False) == []
    assert db.conn.execute("SELECT count(*) FROM device_web_service_checks").fetchone()[0] == 0


def test_mismatched_site_or_ip_does_not_associate_evidence(db):
    found = device(db)
    owner = db.upsert_device(found)
    persist(db, owner, found, [check("192.0.2.99")])
    found.site_id = db.add_site("Other")
    persist(db, owner, found, [check()])
    assert db.list_device_web_services(owner, confirmed_only=False) == []


def test_ipv6_probe_result_persists_against_equivalent_endpoint(db):
    found = device(db, "2001:db8:0:0::1")
    owner = db.upsert_device(found)
    persist(db, owner, found, [check("2001:db8::1")])
    assert len(db.list_device_web_services(owner)) == 1


def test_order_prefers_current_then_https_primary_and_recent():
    rows = web_services_from_checks([check("192.0.2.10", "https", 443), check("192.0.2.11"),
                                    check("192.0.2.12", "https", 443), check("192.0.2.13", "https", 443)])
    rows[0]["last_outcome"] = "failed"
    rows[1]["is_primary"] = True
    rows[2]["last_confirmed_at"] = "2026-09-01T12:00:00+00:00"
    rows[3]["last_confirmed_at"] = "2026-10-01T12:00:00+00:00"
    assert [row["endpoint_ip"] for row in ordered_web_services(rows)] == [
        "192.0.2.13", "192.0.2.12", "192.0.2.11", "192.0.2.10",
    ]
    rows[2]["is_primary"] = True
    assert ordered_web_services(rows)[0]["endpoint_ip"] == "192.0.2.12"


@pytest.fixture
def window(monkeypatch, db):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    view = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(view)
    view.db = db
    view.current_site_id = db.list_sites()[0]["id"]
    view.discovery_site_id = view.current_site_id
    view.discovery_results = []
    view.config_tabs = QTabWidget(view)
    view.setCentralWidget(view.config_tabs)
    for name in ("build_sites_section", "build_equipment_log_panel", "refresh_device_inspector", "refresh_all"):
        monkeypatch.setattr(view, name, Mock())
    monkeypatch.setattr(app_module.QMessageBox, "information", Mock())
    monkeypatch.setattr(app_module.QMessageBox, "warning", Mock())
    monkeypatch.setattr(QMenu, "popup", Mock())
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", Mock(return_value=True))
    view.build_devices_tab()
    view.resize(1500, 1200)
    view.show()
    application.processEvents()
    try:
        yield view
    finally:
        view.hide()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def select_registered(window, *ids):
    window.dev_table.setRowCount(len(ids))
    for row, owner in enumerate(ids):
        item = QTableWidgetItem(str(owner))
        item.setData(Qt.UserRole, owner)
        window.dev_table.setItem(row, 0, item)
    window.dev_table.selectRow(0)
    window._sync_selected_device_actions()


def report(window, found, checks):
    window.discovery_done(services.DiscoveryReport(
        site_id=window.current_site_id, devices=[found], web_results={found.ip: checks},
    ))
    window.devices_found_table.selectRow(0)
    window._discovery_selection_changed()


def web_action(window):
    point = window.dev_table.visualItemRect(window.dev_table.item(0, 0)).center()
    window.show_device_context_menu(point)
    return next(action for action in window._device_context_menu.actions() if action.text() == "Abrir interface Web")


def choose(monkeypatch, index=0, accepted=True, during=None):
    def selection(parent, title, prompt, labels, current, editable):
        assert current == 0 and editable is False
        if during:
            during()
        return labels[index], accepted
    selector = Mock(side_effect=selection)
    monkeypatch.setattr(app_module.QInputDialog, "getItem", selector)
    return selector


def test_registered_web_actions_require_confirmation_not_legacy_url_or_tcp(window):
    found = device(window.db, web_url="https://user:password@192.0.2.10:9443/path", metadata={"open_ports": [80, 443]})
    owner = window.db.upsert_device(found)
    select_registered(window, owner)
    assert not window.web_button.isEnabled()
    assert not web_action(window).isEnabled()
    persist(window.db, owner, found, [check()])
    window._sync_selected_device_actions()
    assert window.web_button.isEnabled()
    assert web_action(window).isEnabled()
    window.open_selected_device_web()
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == "http://192.0.2.10:80/"


@pytest.mark.parametrize("scheme,port", [("http", 8080), ("https", 8443)])
def test_single_confirmed_service_opens_directly_with_exact_safe_url(window, monkeypatch, scheme, port):
    found = device(window.db, web_url="http://user:secret@192.0.2.10/private?token=secret")
    owner = window.db.upsert_device(found)
    persist(window.db, owner, found, [check(scheme=scheme, port=port)])
    selector = choose(monkeypatch)
    select_registered(window, owner)
    window.open_selected_device_web()
    selector.assert_not_called()
    url = app_module.QDesktopServices.openUrl.call_args[0][0]
    assert url.toString() == f"{scheme}://192.0.2.10:{port}/"
    assert not url.userName() and not url.password() and not url.query() and not url.fragment()


@pytest.mark.parametrize("selected,expected", [(0, "https://192.0.2.10:443/"), (1, "http://192.0.2.10:80/")])
def test_multiple_services_offer_https_first_and_allow_http_selection(window, monkeypatch, selected, expected):
    found = device(window.db)
    owner = window.db.upsert_device(found)
    persist(window.db, owner, found, [check(), check(scheme="https", port=443)])
    select_registered(window, owner)
    selector = choose(monkeypatch, selected)
    window.open_selected_device_web()
    labels = selector.call_args[0][3]
    assert labels[0].startswith("HTTPS • 192.0.2.10 • porta 443")
    assert "Confirmação atual" in labels[0]
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == expected


def test_historical_failed_https_is_labeled_after_current_http(window, monkeypatch):
    found = device(window.db)
    owner = window.db.upsert_device(found)
    persist(window.db, owner, found, [check(), check(scheme="https", port=443)])
    persist(window.db, owner, found, [check(scheme="https", port=443, confirmed=False)])
    select_registered(window, owner)
    selector = choose(monkeypatch)
    window.open_selected_device_web()
    labels = selector.call_args[0][3]
    assert labels[0].startswith("HTTP •")
    assert "Confirmação histórica • falha recente" in labels[1]
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == "http://192.0.2.10:80/"


def test_cancel_service_selector_does_not_open_browser(window, monkeypatch):
    found = device(window.db)
    owner = window.db.upsert_device(found)
    persist(window.db, owner, found, [check(), check(scheme="https", port=443)])
    select_registered(window, owner)
    choose(monkeypatch, accepted=False)
    window.open_selected_device_web()
    app_module.QDesktopServices.openUrl.assert_not_called()


@pytest.mark.parametrize("change", ["selection", "site"])
def test_modal_selector_rechecks_device_and_site_before_opening(window, monkeypatch, change):
    found = device(window.db)
    owner = window.db.upsert_device(found)
    other = window.db.upsert_device(device(window.db, "192.0.2.20"))
    persist(window.db, owner, found, [check(), check(scheme="https", port=443)])
    select_registered(window, owner, other)
    def switch():
        if change == "selection":
            window.dev_table.selectRow(1)
        else:
            window.current_site_id = window.db.add_site("Other")
    choose(monkeypatch, during=switch)
    window.open_selected_device_web()
    app_module.QDesktopServices.openUrl.assert_not_called()


def test_unknown_discovery_remains_in_memory_then_inclusion_persists_only_confirmations(window):
    found = device(window.db, web_url="http://192.0.2.10/legacy")
    report(window, found, [check(), check(scheme="https", port=443, confirmed=False)])
    assert window.db.list_devices() == []
    assert window.db.conn.execute("SELECT count(*) FROM device_web_services").fetchone()[0] == 0
    assert window.devices_web_found_btn.isEnabled()
    window.open_discovered_device_web()
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == "http://192.0.2.10:80/"
    window.add_discovered_selected()
    owner = window.db.find_device_by_site_ip(window.current_site_id, found.ip)["id"]
    rows = window.db.list_device_web_services(owner, confirmed_only=False)
    assert len(rows) == 1 and rows[0]["scheme"] == "http"
    assert window.db.get_device(owner)["web_url"] == found.web_url


def test_found_web_button_disabled_for_tcp_and_hint_without_http_confirmation(window):
    found = device(window.db, web_url="http://192.0.2.10/", metadata={"open_ports": [80]})
    report(window, found, [check(confirmed=False)])
    assert not window.devices_web_found_btn.isEnabled()
    window.open_discovered_device_web()
    app_module.QDesktopServices.openUrl.assert_not_called()


def test_known_discovery_uses_report_identity_not_current_selection(window):
    known = device(window.db)
    owner = window.db.upsert_device(known)
    unrelated = window.db.upsert_device(device(window.db, "192.0.2.99"))
    select_registered(window, unrelated)
    report(window, known, [check()])
    assert len(window.db.list_device_web_services(owner)) == 1
    assert window.db.list_device_web_services(unrelated) == []
    assert not window.web_button.isEnabled()


def test_discovery_correlates_secondary_ip_and_persists_on_that_endpoint(window):
    primary = device(window.db, mac="aa:bb:cc:dd:ee:ff")
    owner = window.db.upsert_device(primary)
    found = device(window.db, "192.0.2.20", mac=primary.mac)
    report(window, found, [check(found.ip, "https", 8443)])
    rows = window.db.list_device_web_services(owner)
    assert len(window.db.list_devices()) == 1
    assert len(rows) == 1 and rows[0]["endpoint_ip"] == found.ip
    assert rows[0]["endpoint_id"] == window.db.get_device_endpoint(owner, found.ip)["id"]


def test_registered_legacy_hints_provide_candidates_only_on_matching_endpoint(window):
    primary = device(window.db, web_url="https://192.0.2.10:9443/path?secret=value")
    owner = window.db.upsert_device(primary)
    window.db.register_device_endpoint(owner, ip="192.0.2.20", web_url="http://192.0.2.20:9080/path")
    candidates = window._discovery_web_candidates()
    assert ("https", 9443) in candidates[primary.ip]
    assert ("http", 9080) in candidates["192.0.2.20"]
    assert ("https", 9443) not in candidates["192.0.2.20"]
    assert window.db.list_device_web_services(owner) == []


def test_discovery_worker_receives_registered_candidates(monkeypatch, db):
    found = device(db)
    monkeypatch.setattr(services, "scan_local_cctv", lambda **kw: ([], [], 0))
    monkeypatch.setattr(services, "discover_onvif_devices", lambda site: [found])
    monkeypatch.setattr(services, "apply_device_fingerprint", lambda found: None)
    probe = Mock(side_effect=lambda ip, scheme, port: check(ip, scheme, port))
    monkeypatch.setattr(services, "probe_web_service", probe)
    result = services.discover_network_devices(found.site_id, web_candidates={found.ip: [("https", 9443)]})
    assert probe.call_count == 5
    assert any(item.port == 9443 for item in result.web_results[found.ip])


def test_old_site_report_is_discarded_without_persistence(window):
    known = device(window.db)
    owner = window.db.upsert_device(known)
    origin = window.current_site_id
    window.current_site_id = window.db.add_site("Other")
    window.discovery_done(services.DiscoveryReport(site_id=origin, devices=[known], web_results={known.ip: [check()]}))
    assert window.discovery_results == []
    assert window.db.list_device_web_services(owner) == []


def test_found_selection_change_during_selector_does_not_open_wrong_device(window, monkeypatch):
    found = device(window.db)
    other = device(window.db, "192.0.2.20")
    window.discovery_done(services.DiscoveryReport(
        site_id=window.current_site_id, devices=[found, other],
        web_results={found.ip: [check(), check(scheme="https", port=443)], other.ip: [check(other.ip)]},
    ))
    window.devices_found_table.selectRow(0)
    choose(monkeypatch, during=lambda: window.devices_found_table.selectRow(1))
    window.open_discovered_device_web()
    app_module.QDesktopServices.openUrl.assert_not_called()


def test_changed_site_prevents_inclusion_of_stale_discovery(window):
    found = device(window.db)
    report(window, found, [check()])
    window.current_site_id = window.db.add_site("Other")
    window.add_discovered_selected()
    assert window.db.list_devices() == []


def test_failed_known_probe_preserves_history_and_keeps_registered_web_available(window):
    found = device(window.db)
    owner = window.db.upsert_device(found)
    persist(window.db, owner, found, [check()])
    select_registered(window, owner)
    report(window, found, [check(confirmed=False)])
    assert window.web_button.isEnabled()
    assert "Confirmação histórica" in window.web_button.toolTip()
    assert "Confirmação histórica" in web_action(window).toolTip()
    assert not window.devices_web_found_btn.isEnabled()
    assert window.db.list_device_web_services(owner)[0]["last_outcome"] == "failed"
    window.open_selected_device_web()
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == "http://192.0.2.10:80/"


def test_selector_identifies_unverified_https_certificate(window, monkeypatch):
    found = device(window.db)
    owner = window.db.upsert_device(found)
    unverified = WebProbeResult(found.ip, "https", 443, check().checked_at, True, 401, "unverified", "", 1.0)
    persist(window.db, owner, found, [check(), unverified])
    select_registered(window, owner)
    selector = choose(monkeypatch)
    window.open_selected_device_web()
    assert "certificado não verificado" in selector.call_args[0][3][0]


def test_playback_web_uses_confirmation_even_when_channels_are_already_loaded(window):
    found = device(window.db, web_url="http://192.0.2.10/legacy")
    owner = window.db.upsert_device(found)
    window.playback_device_combo = QComboBox(window)
    window.playback_device_combo.addItem("Camera", owner)
    window.playback_channel_combo = QComboBox(window)
    window.playback_channel_combo.addItem("Channel", 1)
    window.playback_web_button = QPushButton(window)
    window._playback_loaded_device_id = owner
    window.refresh_playback_channels()
    assert not window.playback_web_button.isEnabled()
    persist(window.db, owner, found, [check()])
    window.refresh_playback_channels()
    assert window.playback_web_button.isEnabled()
    window.open_playback_device_web()
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == "http://192.0.2.10:80/"


@pytest.mark.parametrize("ip,metadata,transient", [
    ("192.0.2.10", {}, False),
    ("127.0.0.1", {}, True),
    ("192.0.2.10", {"connection_mode": "site_connector"}, True),
])
def test_registered_endpoint_is_probed_without_lan_rediscovery_or_reclassification(window, monkeypatch, ip, metadata, transient):
    found = device(window.db, ip, web_url=f"http://{ip}:18080/path", metadata=metadata)
    owner = window.db.upsert_device(found)
    select_registered(window, owner)
    monkeypatch.setattr(services, "scan_local_cctv", lambda **kw: ([], [], 0))
    monkeypatch.setattr(services, "discover_onvif_devices", lambda site: [])
    monkeypatch.setattr(services, "probe_web_service", lambda ip, scheme, port: check(ip, scheme, port, port == 18080))
    result = services.discover_network_devices(window.current_site_id, web_candidates=window._discovery_web_candidates())
    assert result.devices == []
    assert len(result.web_results[ip]) == 5
    window.discovery_done(result)
    assert window.discovery_results == []
    assert window.web_button.isEnabled()
    assert len(window.db.list_device_web_services(owner)) == (0 if transient else 1)
    window.open_selected_device_web()
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == f"http://{ip}:18080/"


def test_orphan_web_results_do_not_register_devices(window):
    window.discovery_done(services.DiscoveryReport(
        site_id=window.current_site_id, web_results={"192.0.2.10": [check()]},
    ))
    assert window.db.list_devices() == []
    assert window.db.conn.execute("SELECT count(*) FROM device_web_service_checks").fetchone()[0] == 0


def test_found_results_cannot_enable_or_open_a_different_ip(window):
    found = device(window.db)
    report(window, found, [check("192.0.2.99")])
    assert not window.devices_web_found_btn.isEnabled()
    window.open_discovered_device_web()
    app_module.QDesktopServices.openUrl.assert_not_called()


def test_historical_services_survive_device_correlation(window):
    owner = window.db.upsert_device(device(window.db))
    secondary = device(window.db, "192.0.2.20")
    secondary_id = window.db.upsert_device(secondary)
    persist(window.db, secondary_id, secondary, [check(secondary.ip)])
    persist(window.db, secondary_id, secondary, [check(secondary.ip, confirmed=False)])
    # Model an existing secondary row retained for correlation audit/history.
    with window.db.conn:
        window.db.conn.execute("UPDATE devices SET correlated_to=? WHERE id=?", (owner, secondary_id))
    select_registered(window, owner)
    assert window.web_button.isEnabled()
    assert "Confirmação histórica" in window.web_button.toolTip()
    window.open_selected_device_web()
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == "http://192.0.2.20:80/"


@pytest.mark.parametrize("ip,metadata", [("127.0.0.1", {}), ("192.0.2.10", {"connection_mode": "site_connector"})])
def test_transient_discovery_enables_web_without_persisting(window, ip, metadata):
    found = device(window.db, ip, metadata=metadata)
    owner = window.db.upsert_device(found)
    report(window, found, [check(ip, port=18080)])
    select_registered(window, owner)
    assert window.web_button.isEnabled()
    assert window.devices_web_found_btn.isEnabled()
    assert window.db.list_device_web_services(owner, confirmed_only=False) == []
    window.open_selected_device_web()
    assert app_module.QDesktopServices.openUrl.call_args[0][0].toString() == f"http://{ip}:18080/"

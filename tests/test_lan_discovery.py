from artin_sentinel.lan_discovery import LocalInterface, bounded_scan_hosts, _classify_signature
from artin_sentinel.domain import DeviceKind


def test_bounded_scan_large_network_stays_in_24():
    iface = LocalInterface("eth0", "192.168.15.27", "192.168.0.0/16")
    hosts = bounded_scan_hosts(iface)
    assert "192.168.15.1" in hosts
    assert "192.168.16.1" not in hosts
    assert len(hosts) <= 254


def test_intelbras_http_signature():
    maker, _, kind, evidence = _classify_signature("<title>Intelbras MHDX 1108</title> DVR")
    assert maker == "intelbras"
    assert kind == DeviceKind.DVR
    assert evidence


def test_itblue_signature():
    maker, _, _, _ = _classify_signature("<title>IT-Blue IP Camera</title>")
    assert maker == "IT-Blue"

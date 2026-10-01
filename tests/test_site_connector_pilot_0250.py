from types import SimpleNamespace
import subprocess

import pytest

from artin_sentinel.recorder import RtspProbeReport, scan_intelbras_channels
from artin_sentinel.remote_access import ACCESS_CONNECTOR, access_label, forwarded_ports
from tools.site_tunnel import build_ssh_command, host


def test_connector_endpoints_select_only_registered_host():
    assert forwarded_ports("127.0.0.1", "http://127.0.0.1:18080", "rtsp://127.0.0.1:18554") == (18080, 18554)
    assert forwarded_ports("dvr.local", "http://outro.local:18080", "rtsp://outro.local:18554") == (80, 554)
    assert forwarded_ports("192.168.15.254") == (80, 554)
    assert "conector" in access_label({"connection_mode": ACCESS_CONNECTOR}).lower()
    with pytest.raises(ValueError):
        forwarded_ports("127.0.0.1", "http://user:password@127.0.0.1:18080")


def test_recorder_scan_uses_forwarded_http_and_rtsp_ports(monkeypatch):
    from artin_sentinel import recorder
    seen = []

    def cgi(hostname, _username, _password, timeout):
        seen.append(("http", hostname, timeout))
        return SimpleNamespace(channels=[SimpleNamespace(channel_id=1, name="CAM 1")],
                               ok=True, authenticated=True, detail="CGI OK")

    def rtsp(url, *_args, **_kwargs):
        seen.append(("rtsp", url))
        return RtspProbeReport(True, 200, "SDP OK", first_status=200)

    monkeypatch.setattr(recorder, "probe_intelbras_channel_titles", cgi)
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", rtsp)
    monkeypatch.setattr(recorder, "_audio_fields_for_urls", lambda *_args: {})
    channels = scan_intelbras_channels("127.0.0.1", "admin", "secret", max_channels=1,
                                      http_port=18080, rtsp_port=18554)
    assert len(channels) == 1 and channels[0].available
    assert ("http", "127.0.0.1:18080", 3.0) in seen
    assert all(":18554/" in entry[1] for entry in seen if entry[0] == "rtsp")
    assert ":18554/" in channels[0].main_rtsp_url


def test_ssh_forwarding_only_binds_loopback(tmp_path):
    key = tmp_path / "key"
    key.write_text("test")
    common = dict(identity=str(key), known_hosts=None, ssh_port=22, relay="relay.example",
                  relay_http=24080, relay_rtsp=24554, relay_service=27777)
    site = SimpleNamespace(role="site", ssh_user="site1", dvr="192.168.15.254",
                           dvr_http_port=80, dvr_rtsp_port=554, dvr_service_port=37777, **common)
    operator = SimpleNamespace(role="operator", ssh_user="operator1", local_http=18080,
                               local_rtsp=18554, local_service=37777, **common)
    site_command = build_ssh_command(site)
    operator_command = build_ssh_command(operator)
    assert [site_command[i + 1] for i, arg in enumerate(site_command[:-1]) if arg == "-R"] == [
        "127.0.0.1:24080:192.168.15.254:80",
        "127.0.0.1:24554:192.168.15.254:554",
        "127.0.0.1:27777:192.168.15.254:37777",
    ]
    assert [operator_command[i + 1] for i, arg in enumerate(operator_command[:-1]) if arg == "-L"] == [
        "127.0.0.1:18080:127.0.0.1:24080",
        "127.0.0.1:18554:127.0.0.1:24554",
        "127.0.0.1:37777:127.0.0.1:27777",
    ]
    for command, forwarding in ((site_command, "remoteforward"), (operator_command, "localforward")):
        effective = subprocess.run(command[:-1] + ["-G", "relay.example"],
                                   capture_output=True, text=True, check=True).stdout.lower()
        assert effective.count(forwarding + " ") == 3
    with pytest.raises(Exception):
        host("-oProxyCommand=danger")


def test_loopback_diagnostic_reflects_tunnel_not_local_ping(monkeypatch):
    from artin_sentinel import services
    from artin_sentinel.probes import ProbeResult

    monkeypatch.setattr(services, "ping_probe", lambda *_args: ProbeResult(True, "ICMP OK", 0.1))
    monkeypatch.setattr(services, "tcp_probe", lambda *_args: ProbeResult(False, "closed"))
    monkeypatch.setattr(services, "http_probe", lambda *_args: ProbeResult(False, "unavailable"))
    monkeypatch.setattr(services, "rtsp_options", lambda *_args: ProbeResult(False, "unavailable"))
    params = ("127.0.0.1", "http://127.0.0.1:18080", "rtsp://127.0.0.1:18554")
    assert not services.diagnose(*params).online
    monkeypatch.setattr(services, "rtsp_options", lambda *_args: ProbeResult(True, "RTSP/1.0 401"))
    assert services.diagnose(*params).online

from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import socketserver
import ssl
import threading
from unittest.mock import Mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

from artin_sentinel import __version__
import artin_sentinel.web_services as web


@pytest.fixture
def local_servers():
    running = []

    def start(server):
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        running.append((server, thread))
        return server.server_address[1]

    yield start
    for server, thread in reversed(running):
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def http_server(local_servers, *, status=200, context=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, dict(self.headers)))
            self.send_response(status)
            if status == 301:
                self.send_header("Location", "/redirect-target?token=secret")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    if context:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return local_servers(server), requests


@pytest.fixture
def tls_server(tmp_path, local_servers):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Sentinel local test")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "certificate.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    port, requests = http_server(local_servers, context=context)
    return port, cert_path, requests


@pytest.mark.parametrize("status", [200, 301, 401, 403, 404, 500])
def test_http_status_confirms_service_without_following_redirect(local_servers, status):
    port, requests = http_server(local_servers, status=status)
    result = web.probe_web_service("127.0.0.1", "http", port)
    assert result.confirmed
    assert result.http_status == status
    assert result.tls_status == "not_applicable"
    assert result.error_code == ""
    assert result.latency_ms >= 0
    assert datetime.fromisoformat(result.checked_at).tzinfo is not None
    assert [path for path, _headers in requests] == ["/"]
    headers = requests[0][1]
    assert headers["User-Agent"] == f"Artin-Sentinel/{__version__}"
    assert "Authorization" not in headers
    assert "Cookie" not in headers
    assert not set(asdict(result)).intersection({"url", "headers", "body", "location", "detail"})


def test_https_verified_certificate(tls_server, monkeypatch):
    port, certificate, requests = tls_server
    original = ssl.create_default_context
    monkeypatch.setattr(web.ssl, "create_default_context", lambda: original(cafile=str(certificate)))
    unverified = Mock(side_effect=AssertionError("must not disable certificate verification"))
    monkeypatch.setattr(web.ssl, "_create_unverified_context", unverified)
    result = web.probe_web_service("127.0.0.1", "https", port)
    assert result.confirmed
    assert result.http_status == 200
    assert result.tls_status == "verified"
    assert len(requests) == 1
    unverified.assert_not_called()


def test_https_self_signed_certificate_is_confirmed_without_claiming_trust(tls_server, monkeypatch):
    port, _certificate, requests = tls_server
    original = ssl._create_unverified_context
    fallback = Mock(wraps=original)
    monkeypatch.setattr(web.ssl, "_create_unverified_context", fallback)
    result = web.probe_web_service("127.0.0.1", "https", port)
    assert result.confirmed
    assert result.tls_status == "unverified"
    assert result.error_code == ""
    assert len(requests) == 1
    fallback.assert_called_once_with()


def test_environment_proxies_are_not_used(local_servers, monkeypatch):
    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(key, "http://user:password@127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setenv("NO_PROXY", "")
    port, requests = http_server(local_servers)
    result = web.probe_web_service("127.0.0.1", "http", port)
    assert result.confirmed
    assert len(requests) == 1
    assert "Proxy-Authorization" not in requests[0][1]


def test_tcp_open_without_http_response_does_not_confirm(local_servers):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(4096)
            self.request.sendall(b"not an HTTP response\r\n\r\n")

    port = local_servers(socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler))
    result = web.probe_web_service("127.0.0.1", "http", port)
    assert not result.confirmed
    assert result.http_status is None
    assert result.error_code == "invalid_response"


@pytest.mark.parametrize("exception,code", [
    (TimeoutError("external secret"), "timeout"),
    (ConnectionRefusedError("external secret"), "connection_error"),
    (web.http.client.BadStatusLine("external secret"), "invalid_response"),
    (RuntimeError("http://user:password@host/?token=secret"), "other_error"),
])
def test_failures_are_structured_and_sanitized(monkeypatch, exception, code):
    connection = Mock()
    connection.connect.side_effect = exception
    monkeypatch.setattr(web.http.client, "HTTPConnection", Mock(return_value=connection))
    result = web.probe_web_service("192.0.2.10", "http", 80)
    assert not result.confirmed
    assert result.http_status is None
    assert result.error_code == code
    assert result.tls_status == "not_applicable"
    assert result.latency_ms >= 0
    assert "secret" not in repr(result)
    assert "password" not in repr(result)
    connection.close.assert_called_once_with()


def test_real_tls_error_does_not_retry_unverified(monkeypatch):
    connection = Mock()
    connection.connect.side_effect = ssl.SSLError("handshake failure; external secret")
    factory = Mock(return_value=connection)
    monkeypatch.setattr(web.http.client, "HTTPSConnection", factory)
    fallback = Mock()
    monkeypatch.setattr(web.ssl, "_create_unverified_context", fallback)
    result = web.probe_web_service("192.0.2.10", "https", 443)
    assert not result.confirmed
    assert result.error_code == "tls_error"
    assert result.tls_status == "unverified"
    factory.assert_called_once()
    fallback.assert_not_called()
    connection.close.assert_called_once_with()


def test_certificate_retry_can_fail_with_real_tls_error(monkeypatch):
    first, second = Mock(), Mock()
    first.connect.side_effect = ssl.SSLCertVerificationError("certificate verification failed")
    second.connect.side_effect = ssl.SSLError("real TLS failure")
    factory = Mock(side_effect=[first, second])
    monkeypatch.setattr(web.http.client, "HTTPSConnection", factory)
    result = web.probe_web_service("192.0.2.10", "https", 443)
    assert not result.confirmed
    assert result.error_code == "tls_error"
    assert result.tls_status == "unverified"
    assert factory.call_count == 2
    first.close.assert_called_once_with()
    second.close.assert_called_once_with()


@pytest.mark.parametrize("status", [101, 199, 600, "200"])
def test_invalid_status_does_not_confirm(monkeypatch, status):
    connection = Mock()
    connection.getresponse.return_value.status = status
    monkeypatch.setattr(web.http.client, "HTTPConnection", Mock(return_value=connection))
    result = web.probe_web_service("192.0.2.10", "http", 80)
    assert not result.confirmed
    assert result.error_code == "invalid_response"
    connection.getresponse.return_value.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@pytest.mark.parametrize("ip,scheme,port,expected", [
    ("192.0.2.10", "http", 80, "http://192.0.2.10:80/"),
    ("2001:db8::10", "https", 8443, "https://[2001:db8::10]:8443/"),
])
def test_build_url_for_ipv4_and_ipv6(ip, scheme, port, expected):
    assert web.build_web_service_url(ip, scheme, port) == expected


@pytest.mark.parametrize("ip,scheme,port", [
    ("camera.local", "http", 80),
    ("localhost", "http", 80),
    ("999.0.0.1", "http", 80),
    ("user:password@192.0.2.10", "http", 80),
    ("http://192.0.2.10/", "http", 80),
    ("192.0.2.10/?token=secret", "http", 80),
    ("fe80::1%eth0", "http", 80),
    ("192.0.2.10", "ftp", 80),
    ("192.0.2.10", "http", 0),
    ("192.0.2.10", "http", 65536),
    ("192.0.2.10", "http", True),
    ("192.0.2.10", "http", "80"),
])
def test_invalid_endpoints_are_rejected_before_network(monkeypatch, ip, scheme, port):
    factory = Mock()
    monkeypatch.setattr(web.http.client, "HTTPConnection", factory)
    with pytest.raises(ValueError) as caught:
        web.probe_web_service(ip, scheme, port)
    assert "password" not in str(caught.value)
    assert "secret" not in str(caught.value)
    factory.assert_not_called()


def test_result_is_immutable(monkeypatch):
    connection = Mock()
    connection.getresponse.return_value.status = 200
    monkeypatch.setattr(web.http.client, "HTTPConnection", Mock(return_value=connection))
    result = web.probe_web_service("192.0.2.10", "http", 80)
    with pytest.raises(FrozenInstanceError):
        result.confirmed = False


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_timeout_rejected(timeout):
    with pytest.raises(ValueError):
        web.probe_web_service("192.0.2.10", "http", 80, timeout=timeout)

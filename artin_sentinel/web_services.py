"""HTTP/HTTPS probes and credential-free candidate and selection helpers."""

from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
from ipaddress import ip_address
import math
import ssl
import time
from urllib.parse import urlsplit

from . import __version__


def web_service_candidates(ip: str, web_url: str = "") -> list[tuple[str, int]]:
    """Return explicit probe targets; a configured URL never confirms a service."""
    address = _validated_ip(ip)
    candidates = [("http", 80), ("https", 443), ("http", 8080), ("https", 8443)]
    try:
        hint = urlsplit(web_url.strip())
        if (hint.scheme in ("http", "https") and hint.hostname
                and hint.username is None and hint.password is None
                and _validated_ip(hint.hostname) == address):
            port = hint.port if hint.port is not None else (443 if hint.scheme == "https" else 80)
            build_web_service_url(address, hint.scheme, port)
            if (hint.scheme, port) not in candidates:
                candidates.append((hint.scheme, port))
    except (ValueError, AttributeError):
        pass
    return candidates


def is_transient_web_endpoint(ip: str, metadata: dict) -> bool:
    address = ip_address(_validated_ip(ip))
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(address.is_loopback or address.is_unspecified or (mapped and mapped.is_loopback)
                or metadata.get("connection_mode") == "site_connector"
                or metadata.get("transient"))


def web_services_from_checks(checks, *, is_primary=False, endpoint_ip=None):
    return [dict(endpoint_ip=check.ip, scheme=check.scheme, port=check.port,
                 last_outcome="confirmed", last_confirmed_at=check.checked_at,
                 last_tls_status=check.tls_status, is_primary=is_primary)
            for check in checks if check.confirmed
            and (endpoint_ip is None or _validated_ip(check.ip) == _validated_ip(endpoint_ip))]


def ordered_web_services(services):
    """Keep current confirmations ahead of historical failures and deduplicate."""
    valid = []
    for raw in services:
        service = dict(raw)
        if not service.get("last_confirmed_at"):
            continue
        try:
            build_web_service_url(service["endpoint_ip"], service["scheme"], service["port"])
            confirmed_at = datetime.fromisoformat(service["last_confirmed_at"]).timestamp()
        except (KeyError, ValueError, TypeError):
            continue
        key = (service.get("last_outcome") != "confirmed", service["scheme"] != "https",
               not bool(service.get("is_primary")), -confirmed_at)
        valid.append((key, service))
    valid.sort(key=lambda pair: pair[0])
    selected = {}
    for _key, service in valid:
        selected.setdefault((service["endpoint_ip"], service["scheme"], service["port"]), service)
    return list(selected.values())


@dataclass(frozen=True, slots=True)
class WebProbeResult:
    ip: str
    scheme: str
    port: int
    checked_at: str
    confirmed: bool
    http_status: int | None
    tls_status: str
    error_code: str
    latency_ms: float


def _validated_ip(ip: str) -> str:
    if not isinstance(ip, str) or "%" in ip:
        raise ValueError("Informe um IP literal sem credenciais ou identificador de zona.")
    try:
        return str(ip_address(ip.strip()))
    except ValueError:
        raise ValueError("Informe um endereço IP literal válido.") from None


def build_web_service_url(ip: str, scheme: str, port: int) -> str:
    """Build only a credential-free origin and '/' from validated components."""
    address = _validated_ip(ip)
    if scheme not in ("http", "https"):
        raise ValueError("O esquema deve ser http ou https.")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("A porta deve ser um inteiro entre 1 e 65535.")
    host = f"[{address}]" if ":" in address else address
    return f"{scheme}://{host}:{port}/"


def probe_web_service(ip: str, scheme: str, port: int, *, timeout: float = 2.5) -> WebProbeResult:
    """Confirm an HTTP response, without trusting TCP reachability or redirects.

    Direct http.client connections ignore environment proxies and do not follow
    redirects. Only a certificate verification failure permits a second TLS
    attempt without verification. No response text, headers or credentials are
    returned. A confirmation proves the protocol, not a configuration page.
    """
    build_web_service_url(ip, scheme, port)
    address = _validated_ip(ip)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("O timeout deve ser um número positivo e finito.")
    checked_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    tls_status = "unverified" if scheme == "https" else "not_applicable"
    verify_certificate = True

    def result(error_code: str = "", status: int | None = None) -> WebProbeResult:
        return WebProbeResult(
            ip=address, scheme=scheme, port=port, checked_at=checked_at,
            confirmed=status is not None, http_status=status,
            tls_status=tls_status, error_code=error_code,
            latency_ms=max(0.0, (time.perf_counter() - started) * 1000),
        )

    while True:
        connection = response = None
        try:
            if scheme == "https":
                context = (ssl.create_default_context() if verify_certificate
                           else ssl._create_unverified_context())
                connection = http.client.HTTPSConnection(address, port, timeout=timeout, context=context)
            else:
                connection = http.client.HTTPConnection(address, port, timeout=timeout)
            connection.connect()
            if scheme == "https":
                tls_status = "verified" if verify_certificate else "unverified"
            connection.request("GET", "/", headers={"User-Agent": f"Artin-Sentinel/{__version__}"})
            response = connection.getresponse()
            if type(response.status) is not int or not 200 <= response.status <= 599:
                return result("invalid_response")
            return result(status=response.status)
        except ssl.SSLCertVerificationError:
            if scheme == "https" and verify_certificate:
                verify_certificate = False
                tls_status = "unverified"
                continue
            return result("tls_error")
        except ssl.SSLError:
            return result("tls_error")
        except TimeoutError:
            return result("timeout")
        except http.client.HTTPException:
            return result("invalid_response")
        except OSError:
            return result("connection_error")
        except Exception:
            return result("other_error")
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()

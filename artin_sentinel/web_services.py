"""Isolated HTTP/HTTPS service probes; no persistence or application integration."""

from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
from ipaddress import ip_address
import math
import ssl
import time

from . import __version__


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

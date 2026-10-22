"""Access labels and address checks for manually enrolled remote recorders."""

from ipaddress import ip_address
import re
from urllib.parse import urlparse


ACCESS_LOCAL = "local"
ACCESS_PRIVATE = "private_remote"
ACCESS_CONNECTOR = "site_connector"


def validate_recorder_host(value: str) -> str:
    """Return a bare IP/hostname, without a URL, port or embedded secrets."""
    host = str(value or "").strip()
    if not host or len(host) > 253 or any(c in host for c in "/\\:@?# \t\r\n"):
        raise ValueError("Informe apenas o IP ou nome do gravador, sem porta ou URL.")
    try:
        address = ip_address(host)
    except ValueError:
        if re.fullmatch(r"[0-9.]+", host):
            raise ValueError("Endereço IPv4 inválido.") from None
        if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                   for label in host.rstrip(".").split(".")):
            raise ValueError("IP ou nome do gravador inválido.") from None
        return host.rstrip(".").lower()
    if address.version != 4:
        raise ValueError("Nesta etapa, use IPv4 ou nome de host; rotas IPv6 ainda não são suportadas.")
    return str(address)


def validate_endpoint_url(value: str, *, schemes: tuple[str, ...]) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in schemes or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL inválida ou contendo credencial; informe a senha no diálogo de leitura de canais.")
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("A porta da URL é inválida.") from None
    return url


def discovered_web_url(value: str, device_ip: str) -> str:
    """Allow opening only the discovered device's credential-free Web endpoint."""
    try:
        url = validate_endpoint_url(value, schemes=("http", "https"))
        if url and urlparse(url).hostname == str(device_ip or "").strip().lower():
            return url
    except ValueError:
        pass
    return ""


def access_label(metadata: dict) -> str:
    mode = metadata.get("connection_mode")
    if mode == "intelbras_cloud_bridge":
        return "Acesso: Intelbras Cloud via Wine (piloto)" if metadata.get("wine_managed") else "Acesso: Intelbras Cloud via ponte (piloto)"
    if mode == ACCESS_CONNECTOR:
        return "Acesso: conector por Site"
    return "Acesso: remoto por rede privada/VPN" if mode == ACCESS_PRIVATE else "Acesso: rede local"


def forwarded_ports(host: str, web_url: str = "", rtsp_url: str = "") -> tuple[int, int]:
    """Return HTTP/RTSP ports only for endpoints on the registered host.

    A separate endpoint must never silently redirect discovery or credentials
    to another host. Existing direct registrations keep ports 80 and 554.
    """
    def selected(url: str, schemes: tuple[str, ...], default: int) -> int:
        if not url:
            return default
        parsed = urlparse(validate_endpoint_url(url, schemes=schemes))
        if parsed.hostname != str(host).strip().lower():
            return default
        return parsed.port or default
    return selected(web_url, ("http", "https"), 80), selected(rtsp_url, ("rtsp", "rtsps"), 554)


def preserve_remote_inventory(is_remote: bool, prior_channels, scanned_channels) -> bool:
    """Keep reconnectable channels when a remote read confirms no new video."""
    return bool(is_remote and prior_channels and not any(ch.available for ch in scanned_channels))

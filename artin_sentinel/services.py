from __future__ import annotations
import json
from ipaddress import ip_address
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from .domain import Device, DeviceStatus, DeviceKind
from .onvif import discover
from .providers import classify_from_scopes, pick_provider
from .probes import ping_probe, tcp_probe, http_probe, rtsp_options
from .lan_discovery import scan_local_cctv, HostObservation
from .fingerprint import apply_device_fingerprint
from .web_services import WebProbeResult, web_service_candidates, probe_web_service, is_transient_web_endpoint

COMMON_PORTS = (80, 443, 554, 8000, 8080, 8899, 34567, 37777)


@dataclass(slots=True)
class DiagnosticSummary:
    online: bool
    ping_ok: bool
    latency_ms: float | None
    open_ports: list[int]
    web_ok: bool | None
    rtsp_ok: bool | None
    details: list[str]
    active_ip: str = ""
    endpoint_statuses: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DiscoveryReport:
    interfaces: list[str] = field(default_factory=list)
    addresses_scanned: int = 0
    responsive_hosts: int = 0
    other_hosts: list[str] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    site_id: int | None = None
    web_results: dict[str, list[WebProbeResult]] = field(default_factory=dict)


def probe_discovered_web_services(device: Device, extra_candidates=()) -> list[WebProbeResult]:
    try:
        candidates = web_service_candidates(device.ip, device.web_url)
    except ValueError:
        return []
    for candidate in extra_candidates:
        if candidate not in candidates:
            candidates.append(candidate)
    return [probe_web_service(device.ip, scheme, port) for scheme, port in candidates]


def persist_discovered_web_checks(db, device_id: int, device: Device, checks, *, confirmed_only=False):
    """Persist only evidence belonging to this existing equipment and endpoint."""
    if not checks:
        return
    try:
        address = ip_address(device.ip.strip())
        checks = [check for check in checks if ip_address(check.ip) == address
                  and (not confirmed_only or check.confirmed)]
    except ValueError:
        return
    if not checks:
        return
    owner = db.get_device(device_id)
    if owner is None or owner["site_id"] != device.site_id:
        return
    metadata = json.loads(owner["metadata_json"] or "{}")
    if (is_transient_web_endpoint(device.ip, metadata)
            or is_transient_web_endpoint(device.ip, device.metadata)):
        return
    endpoint = db.get_device_endpoint(device_id, device.ip)
    if endpoint is None:
        db.register_device_endpoint(device_id, ip=device.ip, metadata=device.metadata,
                                    web_url=device.web_url, rtsp_url=device.rtsp_url,
                                    onvif_url=device.onvif_url)
        endpoint = db.get_device_endpoint(device_id, device.ip)
    for check in checks:
        db.record_web_service_check(
            endpoint["id"], ip=check.ip, scheme=check.scheme, port=check.port,
            confirmed=check.confirmed, http_status=check.http_status,
            tls_status=check.tls_status, error_code=check.error_code, latency_ms=check.latency_ms,
        )


def discover_onvif_devices(site_id: int) -> list[Device]:
    devices = []
    for result in discover():
        kind, manufacturer, model = classify_from_scopes(result.scopes)
        web = ""
        for xaddr in result.xaddrs:
            if xaddr.startswith(("http://", "https://")):
                web = xaddr
                break

        device = Device(
            site_id=site_id,
            name=model or manufacturer or f"ONVIF {result.ip}",
            ip=result.ip,
            manufacturer=manufacturer,
            model=model,
            kind=kind,
            status=DeviceStatus.ONLINE,
            onvif_url=web,
            web_url=web,
            metadata={
                "scopes": result.scopes,
                "xaddrs": result.xaddrs,
                "endpoint": result.endpoint,
                "discovery_sources": ["onvif-ws-discovery"],
            },
        )
        devices.append(pick_provider(device))
    return devices


def _device_from_observation(site_id: int, obs: HostObservation) -> Device:
    device = Device(
        site_id=site_id,
        name=obs.model or obs.manufacturer or f"Possível CFTV {obs.ip}",
        ip=obs.ip,
        mac=obs.mac,
        manufacturer=obs.manufacturer,
        model=obs.model,
        kind=obs.kind,
        status=DeviceStatus.ONLINE,
        onvif_url=obs.onvif_url,
        web_url=obs.web_url,
        rtsp_url=obs.rtsp_url,
        metadata={
            "interface": obs.interface,
            "open_ports": obs.open_ports,
            "evidence": obs.evidence,
            "discovery_sources": ["lan-service-scan"],
        },
    )
    return pick_provider(device)


def _merge_device(existing: Device, incoming: Device) -> Device:
    # Prefer ONVIF semantic data, but preserve useful service discovery evidence.
    for attr in ("mac", "manufacturer", "model", "onvif_url", "web_url", "rtsp_url"):
        if not getattr(existing, attr) and getattr(incoming, attr):
            setattr(existing, attr, getattr(incoming, attr))
    if incoming.kind in (DeviceKind.DVR, DeviceKind.NVR, DeviceKind.XVR):
        # Semantic ONVIF recorder evidence outranks the generic LAN heuristic
        # that may have called any RTSP host a camera.
        existing.kind = incoming.kind
    elif existing.kind == DeviceKind.UNKNOWN and incoming.kind != DeviceKind.UNKNOWN:
        existing.kind = incoming.kind
    if existing.name.startswith(("Possível CFTV", "ONVIF ")) and incoming.name:
        existing.name = incoming.name
    merged = dict(existing.metadata)
    for key, value in incoming.metadata.items():
        if key == "discovery_sources":
            merged[key] = sorted(set(merged.get(key, []) + value))
        elif key == "evidence":
            merged[key] = list(dict.fromkeys(merged.get(key, []) + value))
        elif key == "open_ports":
            merged[key] = sorted(set(merged.get(key, []) + value))
        elif not merged.get(key):
            merged[key] = value
    existing.metadata = merged
    return pick_provider(existing)


def discover_network_devices(site_id: int, progress=None, *, web_candidates=None) -> DiscoveryReport:
    report = DiscoveryReport(site_id=site_id)
    merged: dict[str, Device] = {}

    if progress:
        progress("1/3 — Identificando interfaces e serviços locais…")
    interfaces, observations, total = scan_local_cctv(progress=progress)
    report.interfaces = [f"{i.name} {i.address} ({i.network})" for i in interfaces]
    report.addresses_scanned = total
    report.responsive_hosts = len(observations)

    for obs in observations:
        if not obs.looks_like_cctv:
            report.other_hosts.append(f"{obs.ip} • portas {','.join(map(str, obs.open_ports)) or '—'}")
            continue
        device = _device_from_observation(site_id, obs)
        merged[device.ip] = device

    if progress:
        progress("2/3 — Executando ONVIF WS-Discovery…")
    try:
        onvif_devices = discover_onvif_devices(site_id)
    except Exception as exc:
        onvif_devices = []
        if progress:
            progress(f"WS-Discovery não respondeu: {type(exc).__name__}: {exc}")

    for device in onvif_devices:
        if device.ip in merged:
            merged[device.ip] = _merge_device(merged[device.ip], device)
        else:
            merged[device.ip] = device

    if progress:
        progress("3/3 — Consultando AKDB e consolidando identidade…")

    for device in merged.values():
        apply_device_fingerprint(device)

    if progress:
        progress("Confirmando serviços HTTP/HTTPS dos equipamentos identificados…")
    web_targets = dict(merged)
    for ip in web_candidates or {}:
        # Registered endpoints can be outside the LAN scan (including tunnels).
        # Probe evidence does not add them to the CFTV discovery classification.
        web_targets.setdefault(ip, Device(site_id=site_id, ip=ip))
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = {pool.submit(probe_discovered_web_services, device,
                             (web_candidates or {}).get(device.ip, ())): device.ip
                 for device in web_targets.values()}
        for future in as_completed(tasks):
            report.web_results[tasks[future]] = future.result()

    report.other_hosts = [host for host in report.other_hosts if host.split(" • ", 1)[0] not in merged]
    report.devices = sorted(merged.values(), key=lambda d: tuple(int(x) if x.isdigit() else x for x in d.ip.split(".")))
    return report


def diagnose(ip: str, web_url: str = "", rtsp_url: str = "") -> DiagnosticSummary:
    ping = ping_probe(ip)
    open_ports: list[int] = []
    details = [ping.detail]

    for port in COMMON_PORTS:
        result = tcp_probe(ip, port, 0.7)
        if result.ok:
            open_ports.append(port)

    web_ok = None
    if web_url:
        result = http_probe(web_url)
        web_ok = result.ok
        details.append(result.detail)
    elif 80 in open_ports:
        result = http_probe(f"http://{ip}/")
        web_ok = result.ok
        details.append(result.detail)
    elif 443 in open_ports:
        result = http_probe(f"https://{ip}/")
        web_ok = result.ok
        details.append(result.detail)

    rtsp_ok = None
    if rtsp_url:
        result = rtsp_options(rtsp_url)
        rtsp_ok = result.ok
        details.append(result.detail)
    elif 554 in open_ports:
        result = rtsp_options(f"rtsp://{ip}:554/")
        rtsp_ok = result.ok
        details.append(result.detail)

    # A loopback host describes the operator's tunnel endpoint, not the DVR.
    # Ping on 127.0.0.1 succeeds even if either SSH connection is gone.
    loopback_tunnel = ip.startswith("127.") and bool(web_url or rtsp_url)
    online = bool(web_ok or rtsp_ok) if loopback_tunnel else bool(ping.ok or open_ports)
    if loopback_tunnel:
        details.append("Conector local: disponibilidade calculada pelas URLs encaminhadas, não pelo ping do computador.")
    return DiagnosticSummary(
        online=online,
        ping_ok=ping.ok,
        latency_ms=ping.latency_ms,
        open_ports=open_ports,
        web_ok=web_ok,
        rtsp_ok=rtsp_ok,
        details=details,
    )


def diagnose_endpoints(endpoints, fallback_ip: str = "", fallback_web: str = "", fallback_rtsp: str = "") -> DiagnosticSummary:
    """Diagnose one physical device through all known network endpoints.

    A physical device is online when at least one endpoint answers. Endpoint
    checks run concurrently so a secondary IP does not double the 30 s monitor
    cycle latency.
    """
    normalized = []
    for ep in endpoints or []:
        if isinstance(ep, dict):
            normalized.append({
                "ip": str(ep.get("ip") or ""),
                "web_url": str(ep.get("web_url") or ""),
                "rtsp_url": str(ep.get("rtsp_url") or ""),
            })
        else:
            try:
                normalized.append({
                    "ip": str(ep["ip"] or ""),
                    "web_url": str(ep["web_url"] or ""),
                    "rtsp_url": str(ep["rtsp_url"] or ""),
                })
            except Exception:
                continue
    normalized = [ep for ep in normalized if ep["ip"]]
    if not normalized and fallback_ip:
        normalized = [{"ip": fallback_ip, "web_url": fallback_web, "rtsp_url": fallback_rtsp}]
    if not normalized:
        return DiagnosticSummary(False, False, None, [], None, None, ["Nenhum endpoint disponível"], fallback_ip, {})

    results: dict[str, DiagnosticSummary] = {}
    workers = min(4, len(normalized))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sentinel-endpoint") as pool:
        future_map = {
            pool.submit(diagnose, ep["ip"], ep["web_url"], ep["rtsp_url"]): ep["ip"]
            for ep in normalized
        }
        for future in as_completed(future_map):
            ip = future_map[future]
            try:
                results[ip] = future.result()
            except Exception as exc:
                results[ip] = DiagnosticSummary(
                    False, False, None, [], None, None,
                    [f"Falha ao diagnosticar endpoint: {type(exc).__name__}: {exc}"],
                )

    statuses = {ip: ("online" if result.online else "offline") for ip, result in results.items()}
    primary_order = [ep["ip"] for ep in normalized]
    active_ip = next((ip for ip in primary_order if results.get(ip) and results[ip].online), "")
    chosen_ip = active_ip or primary_order[0]
    chosen = results[chosen_ip]
    chosen.active_ip = chosen_ip
    chosen.endpoint_statuses = statuses
    if len(normalized) > 1:
        chosen.details = list(chosen.details) + [
            "Endpoints: " + ", ".join(f"{ip}={statuses.get(ip, 'unknown')}" for ip in primary_order)
        ]
    return chosen

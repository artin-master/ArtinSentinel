from __future__ import annotations

import ipaddress
import json
import re
import socket
import ssl
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import __version__
from .domain import DeviceKind

# Conservative, read-only service probes commonly seen in CCTV equipment.
COMMON_CCTV_PORTS = (80, 443, 554, 8000, 8080, 8899, 34567, 37777)


@dataclass(slots=True)
class LocalInterface:
    name: str
    address: str
    network: str


@dataclass(slots=True)
class HostObservation:
    ip: str
    interface: str = ""
    mac: str = ""
    open_ports: list[int] = field(default_factory=list)
    manufacturer: str = ""
    model: str = ""
    kind: DeviceKind = DeviceKind.UNKNOWN
    web_url: str = ""
    rtsp_url: str = ""
    onvif_url: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def looks_like_cctv(self) -> bool:
        if self.onvif_url or self.rtsp_url:
            return True
        if any(p in self.open_ports for p in (34567, 37777)):
            return True
        text = " ".join(self.evidence).lower()
        return any(
            token in text
            for token in (
                "camera", "dvr", "nvr", "xvr", "onvif", "rtsp",
                "netsurveillance", "ipc", "modelo encontrado na interface web",
            )
        )


def _run_json(*args: str):
    try:
        cp = subprocess.run(
            list(args), capture_output=True, text=True, timeout=3, check=False
        )
        if cp.returncode != 0 or not cp.stdout.strip():
            return []
        return json.loads(cp.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def detect_local_interfaces() -> list[LocalInterface]:
    """Return active private IPv4 interfaces using the Linux `ip` command."""
    rows = _run_json("ip", "-j", "-4", "addr", "show", "up")
    out: list[LocalInterface] = []
    for row in rows:
        name = row.get("ifname", "")
        if name == "lo":
            continue
        for addr in row.get("addr_info", []):
            if addr.get("family") != "inet":
                continue
            local = addr.get("local", "")
            prefix = int(addr.get("prefixlen", 32))
            try:
                ip = ipaddress.ip_address(local)
                network = ipaddress.ip_network(f"{local}/{prefix}", strict=False)
            except ValueError:
                continue
            if not (ip.is_private or ip.is_link_local):
                continue
            out.append(LocalInterface(name=name, address=local, network=str(network)))
    return out


def read_neighbors() -> dict[str, tuple[str, str]]:
    """Return IPv4 -> (MAC, interface) from the kernel neighbor table."""
    rows = _run_json("ip", "-j", "-4", "neigh", "show")
    result: dict[str, tuple[str, str]] = {}
    for row in rows:
        ip = row.get("dst", "")
        mac = row.get("lladdr", "")
        dev = row.get("dev", "")
        try:
            if not ipaddress.ip_address(ip).is_private:
                continue
        except ValueError:
            continue
        result[ip] = (mac, dev)
    return result


def bounded_scan_hosts(interface: LocalInterface, max_hosts: int = 254) -> list[str]:
    """Build a bounded host list; large LANs are limited to the interface's /24."""
    ip = ipaddress.ip_address(interface.address)
    network = ipaddress.ip_network(interface.network, strict=False)
    if network.num_addresses - 2 > max_hosts:
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
    return [str(host) for host in network.hosts() if host != ip][:max_hosts]


def _tcp_open(ip: str, port: int, timeout: float = 0.22) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_signature(ip: str, port: int, timeout: float = 0.7) -> tuple[str, str]:
    scheme = "https" if port == 443 else "http"
    url = f"{scheme}://{ip}:{port}/" if port not in (80, 443) else f"{scheme}://{ip}/"
    context = ssl._create_unverified_context() if scheme == "https" else None
    req = Request(url, headers={"User-Agent": f"Artin-Sentinel/{__version__}"})
    try:
        response = urlopen(req, timeout=timeout, context=context)
        data = response.read(8192).decode("latin1", "replace")
        server = response.headers.get("Server", "")
        response.close()
        return data, server
    except HTTPError as exc:
        try:
            data = exc.read(4096).decode("latin1", "replace")
        except Exception:
            data = ""
        return data, exc.headers.get("Server", "") if exc.headers else ""
    except Exception:
        return "", ""


def _probe_onvif_endpoint(ip: str, ports: list[int]) -> str:
    candidates = []
    for port in ports:
        if port in (80, 8080, 8899):
            base = f"http://{ip}" if port == 80 else f"http://{ip}:{port}"
            candidates.append(base + "/onvif/device_service")
        elif port == 443:
            candidates.append(f"https://{ip}/onvif/device_service")
    for url in candidates:
        context = ssl._create_unverified_context() if url.startswith("https://") else None
        req = Request(url, method="GET", headers={"User-Agent": f"Artin-Sentinel/{__version__}"})
        try:
            response = urlopen(req, timeout=0.65, context=context)
            code = getattr(response, "status", 200)
            response.close()
            if code != 404:
                return url
        except HTTPError as exc:
            # Authentication / method errors still prove that the ONVIF endpoint exists.
            if exc.code in (400, 401, 403, 405, 500):
                return url
        except Exception:
            pass
    return ""


def _classify_signature(text: str) -> tuple[str, str, DeviceKind, list[str]]:
    low = text.lower()
    maker = ""
    model = ""
    kind = DeviceKind.UNKNOWN
    evidence: list[str] = []

    signatures = (
        ("intelbras", ("intelbras", "mhdx", "nvd ", "vip ")),
        ("hikvision", ("hikvision", "dvrdvs-webs", "hikvision-webs")),
        ("jfl", ("jfl",)),
        ("haiz", ("haiz",)),
        ("positivo", ("positivo",)),
        ("Aitek", ("aitek", "aiktek")),
        ("IT-Blue", ("it-blue", "it blue")),
    )
    for name, tokens in signatures:
        if any(token in low for token in tokens):
            maker = name
            evidence.append(f"assinatura HTTP compatível com {name}")
            break

    if re.search(r"\b(nvr|network video recorder)\b", low):
        kind = DeviceKind.NVR
    elif re.search(r"\b(dvr|digital video recorder)\b", low):
        kind = DeviceKind.DVR
    elif re.search(r"\b(xvr|hybrid recorder)\b", low):
        kind = DeviceKind.XVR
    elif re.search(r"\b(ip camera|network camera|ipc|camera)\b", low):
        kind = DeviceKind.CAMERA

    # Prefer explicit model strings found anywhere in the page/JS over a
    # generic <title>Intelbras</title>. This helps older MHDX interfaces that
    # embed the product identifier in scripts rather than the title.
    explicit_model = re.search(r"\b(MHDX[\s_-]*\d{4}(?:[-\s]?C)?)\b", text, re.I)
    if explicit_model:
        model = re.sub(r"[\s_]+", " ", explicit_model.group(1).upper()).replace("MHDX-", "MHDX ")
        evidence.append(f"modelo encontrado na interface web: {model}")
        if kind == DeviceKind.UNKNOWN:
            kind = DeviceKind.XVR

    vipc = re.search(r"\b(VIPC[\s_-]*1230[\s_-]*D[\s_-]*G2)\b", text, re.I)
    if vipc:
        maker = maker or "intelbras"
        model = "VIPC 1230 D G2"
        evidence.append("modelo encontrado na interface web: VIPC 1230 D G2")
        kind = DeviceKind.CAMERA

    hik = re.search(r"\b(DS[\s_-]*7216HGHI[\s_-]*F1)\b", text, re.I)
    if hik:
        maker = maker or "hikvision"
        model = "DS-7216HGHI-F1"
        evidence.append("modelo encontrado na interface web: DS-7216HGHI-F1")
        if kind == DeviceKind.UNKNOWN:
            kind = DeviceKind.XVR

    h2 = re.search(r"\b(H2[\s_-]*52PGX)\b", text, re.I)
    if h2:
        model = "H2-52PGX"
        evidence.append("modelo/plataforma encontrado na interface web: H2-52PGX")
        if kind == DeviceKind.UNKNOWN and re.search(r"\b(IPC|IP CAMERA|NETWORK CAMERA|CAMERA)\b", text, re.I):
            kind = DeviceKind.CAMERA

    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    if title:
        clean = re.sub(r"\s+", " ", title.group(1)).strip()
        if 1 <= len(clean) <= 80:
            if not model:
                model = clean
            evidence.append(f"título web: {clean}")
    return maker, model, kind, evidence


def probe_host(ip: str, interface: str = "", mac: str = "") -> HostObservation:
    open_ports = [p for p in COMMON_CCTV_PORTS if _tcp_open(ip, p)]
    obs = HostObservation(ip=ip, interface=interface, mac=mac, open_ports=open_ports)
    if not open_ports:
        return obs

    obs.evidence.append("portas: " + ", ".join(map(str, open_ports)))

    web_port = next((p for p in (80, 443, 8080) if p in open_ports), None)
    if web_port:
        scheme = "https" if web_port == 443 else "http"
        obs.web_url = (
            f"{scheme}://{ip}/" if web_port in (80, 443)
            else f"{scheme}://{ip}:{web_port}/"
        )
        body, server = _http_signature(ip, web_port)
        maker, model, kind, evidence = _classify_signature(f"{server}\n{body}")
        obs.manufacturer = maker
        obs.model = model
        obs.kind = kind
        obs.evidence.extend(evidence)
        if server:
            obs.evidence.append(f"HTTP Server: {server[:100]}")

    if 554 in open_ports:
        obs.rtsp_url = f"rtsp://{ip}:554/"
        obs.evidence.append("porta RTSP respondeu; mídia/câmera ainda não confirmada")

    obs.onvif_url = _probe_onvif_endpoint(ip, open_ports)
    if obs.onvif_url:
        obs.evidence.append("endpoint ONVIF detectado")
        if obs.kind == DeviceKind.UNKNOWN:
            obs.kind = DeviceKind.CAMERA

    if obs.kind == DeviceKind.UNKNOWN and any(p in open_ports for p in (8000, 34567, 37777)):
        obs.evidence.append("porta de serviço comum em equipamentos de vídeo")

    # Shared service ports alone do not establish manufacturer identity.
    if 8000 in open_ports and 554 in open_ports and any(p in open_ports for p in (80, 443)):
        obs.evidence.append("portas 80/443 + 554 + 8000; fabricante não confirmado")

    # Field fingerprint: simple Aitek cameras must not be promoted to NVR just
    # because generic recorder URLs happen to answer with the same stream.
    if obs.manufacturer.lower() == "aitek":
        obs.kind = DeviceKind.CAMERA
        obs.evidence.append("AKDB: Aitek validada como câmera IP simples (1 canal lógico por padrão)")

    # Common generic OEM web title seen on an IT-Blue field camera. Keep this
    # probabilistic and only apply when the service combination matches.
    evidence_text = " ".join(obs.evidence).lower()
    if obs.model.lower() == "web viewer" and 554 in open_ports and 34567 in open_ports:
        obs.manufacturer = obs.manufacturer or "IT-Blue"
        obs.kind = DeviceKind.CAMERA
        obs.evidence.append("AKDB: Web Viewer + RTSP + 34567 compatível com câmera IT-Blue")

    # Intelbras cameras and recorders may both expose 37777.  Do not promote
    # every Intelbras host with that port to XVR: Mibo/iMX cameras seen in field
    # tests expose RTSP + ONVIF + 37777 as well.  Explicit recorder semantics
    # (MHDX/NVD/DVR/NVR/XVR) win; otherwise an ONVIF endpoint keeps the device
    # on the camera path until stronger evidence appears.
    if 37777 in open_ports and obs.manufacturer.lower() == "intelbras":
        text = f"{obs.model} {' '.join(obs.evidence)}".lower()
        recorder_tokens = ("mhdx", "nvd ", " dvr", " nvr", " xvr", "gravador")
        camera_tokens = ("mibo", "imx", "ip camera", "ipc", "vip ")
        if any(token in text for token in recorder_tokens):
            obs.kind = DeviceKind.XVR
            obs.evidence.append("classificação de gravador por evidência semântica Intelbras + 37777")
        elif any(token in text for token in camera_tokens) or obs.onvif_url:
            obs.kind = DeviceKind.CAMERA
            obs.evidence.append("classificação conservadora de câmera: ONVIF/assinatura sem evidência de gravador")
        else:
            obs.evidence.append("Intelbras + 37777 detectado; tipo mantido conservador até evidência câmera/gravador")

    return obs


def scan_local_cctv(progress=None, max_workers: int = 64) -> tuple[list[LocalInterface], list[HostObservation], int]:
    interfaces = detect_local_interfaces()
    neighbors = read_neighbors()
    targets: dict[str, tuple[str, str]] = {}

    for iface in interfaces:
        if progress:
            progress(f"Interface {iface.name}: {iface.address} — rede {iface.network}")
        for ip in bounded_scan_hosts(iface):
            mac, dev = neighbors.get(ip, ("", iface.name))
            targets[ip] = (dev or iface.name, mac)

    # Keep neighbors even if their interface address could not be enumerated.
    for ip, (mac, dev) in neighbors.items():
        targets.setdefault(ip, (dev, mac))

    total = len(targets)
    if progress:
        progress(f"Varredura local limitada: {total} endereço(s) candidato(s).")

    observations: list[HostObservation] = []
    if not targets:
        return interfaces, observations, 0

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sentinel-discovery") as executor:
        futures = {
            executor.submit(probe_host, ip, iface, mac): ip
            for ip, (iface, mac) in targets.items()
        }
        for future in as_completed(futures):
            try:
                obs = future.result()
            except Exception:
                continue
            if obs.open_ports:
                observations.append(obs)
                if progress and obs.looks_like_cctv:
                    services = ",".join(map(str, obs.open_ports))
                    progress(f"Possível CFTV: {obs.ip} — portas {services}")

    observations.sort(key=lambda item: ipaddress.ip_address(item.ip))
    return interfaces, observations, total

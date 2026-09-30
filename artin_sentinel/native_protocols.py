from __future__ import annotations

"""Read-only native protocol plans.

This module deliberately describes safe local probes instead of automatically
executing vendor commands.  It gives providers a single place to expose native
LAN integration candidates while keeping writes/configuration out of scope.
"""

from dataclasses import dataclass
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import (
    Request, build_opener, HTTPDigestAuthHandler, HTTPBasicAuthHandler,
    HTTPPasswordMgrWithDefaultRealm, HTTPSHandler,
)
from xml.etree import ElementTree as ET


@dataclass(frozen=True, slots=True)
class NativeProtocolPlan:
    key: str
    provider: str
    label: str
    transport: str
    read_only: bool = True
    endpoints: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


PLANS: tuple[NativeProtocolPlan, ...] = (
    NativeProtocolPlan(
        key="hikvision-isapi-readonly-candidate",
        provider="hikvision",
        label="Hikvision ISAPI (somente leitura)",
        transport="HTTP/HTTPS Digest",
        endpoints=(
            "/ISAPI/System/deviceInfo",
            "/ISAPI/System/Video/inputs/channels",
            "/ISAPI/ContentMgmt/InputProxy/channels",
            "/ISAPI/ContentMgmt/InputProxy/channels/status",
            "/ISAPI/Streaming/channels",
        ),
        notes=("consultas GET/XML somente; nenhuma alteração remota é permitida neste estágio",),
    ),
    NativeProtocolPlan(
        key="hikvision-service-8000",
        provider="hikvision",
        label="Hikvision service 8000",
        transport="TCP proprietário",
        endpoints=(),
        notes=("presença da porta é evidência; comandos binários permanecem desabilitados até validação específica",),
    ),
    NativeProtocolPlan(
        key="intelbras-cgi-readonly-candidate",
        provider="intelbras",
        label="Intelbras CGI (somente leitura, candidato)",
        transport="HTTP/HTTPS Digest",
        endpoints=("/cgi-bin/magicBox.cgi?action=getSystemInfo",),
        notes=("endpoint deve ser confirmado por modelo/firmware antes de uso automático",),
    ),
    NativeProtocolPlan(
        key="intelbras-dahua-cgi-readonly-candidate",
        provider="intelbras",
        label="Intelbras/Dahua CGI (somente leitura, candidato)",
        transport="HTTP/HTTPS Digest",
        endpoints=("/cgi-bin/magicBox.cgi?action=getSystemInfo",),
        notes=("família MHDX/Dahua-like; não executar ações de configuração",),
    ),
)


def plans_for(provider: str, protocol_keys: list[str] | tuple[str, ...] = ()) -> list[NativeProtocolPlan]:
    wanted = set(protocol_keys or ())
    out = []
    for plan in PLANS:
        if provider and plan.provider != provider:
            continue
        if wanted and plan.key not in wanted:
            continue
        out.append(plan)
    return out


@dataclass(frozen=True, slots=True)
class NativeHttpProbeResult:
    ok: bool = False
    authenticated: bool = False
    status_code: int | None = None
    endpoint: str = ""
    manufacturer: str = ""
    model: str = ""
    device_name: str = ""
    firmware: str = ""
    detail: str = ""


def _xml_text(root: ET.Element, local_name: str) -> str:
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1].lower() == local_name.lower():
            return (elem.text or "").strip()
    return ""


def probe_hikvision_isapi_device_info(ip: str, username: str, password: str, timeout: float = 3.5) -> NativeHttpProbeResult:
    """Authenticate one read-only Hikvision ISAPI endpoint.

    This probe is intentionally GET-only.  It is used to separate an RTSP/path
    failure from an actual credential failure during recorder onboarding.
    """
    last_detail = "ISAPI não respondeu"
    last_status = None
    for scheme in ("http", "https"):
        endpoint = f"{scheme}://{ip}/ISAPI/System/deviceInfo"
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, endpoint, username or "admin", password or "")
        handlers = [HTTPDigestAuthHandler(manager), HTTPBasicAuthHandler(manager)]
        if scheme == "https":
            handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
        opener = build_opener(*handlers)
        req = Request(endpoint, method="GET", headers={"User-Agent": "Artin-Sentinel/0.2.24"})
        try:
            with opener.open(req, timeout=timeout) as response:
                status = int(getattr(response, "status", 200) or 200)
                payload = response.read(256 * 1024)
            if status < 200 or status >= 300:
                last_status = status
                last_detail = f"ISAPI retornou HTTP {status}"
                continue
            try:
                root = ET.fromstring(payload)
            except ET.ParseError:
                root = None
            return NativeHttpProbeResult(
                ok=True, authenticated=True, status_code=status, endpoint=endpoint,
                manufacturer=_xml_text(root, "manufacturer") if root is not None else "",
                model=_xml_text(root, "model") if root is not None else "",
                device_name=_xml_text(root, "deviceName") if root is not None else "",
                firmware=_xml_text(root, "firmwareVersion") if root is not None else "",
                detail="ISAPI autenticada com sucesso",
            )
        except HTTPError as exc:
            last_status = int(exc.code)
            if exc.code == 401:
                last_detail = "ISAPI respondeu, mas rejeitou a credencial (HTTP 401)"
            elif exc.code == 403:
                last_detail = "ISAPI respondeu, mas o usuário não possui permissão para esta consulta (HTTP 403)"
            else:
                last_detail = f"ISAPI retornou HTTP {exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            last_detail = f"ISAPI {scheme.upper()} indisponível: {type(exc).__name__}"
    return NativeHttpProbeResult(
        ok=False, authenticated=False, status_code=last_status, detail=last_detail
    )


@dataclass(frozen=True, slots=True)
class HikvisionStreamingInventory:
    ok: bool = False
    authenticated: bool = False
    status_code: int | None = None
    endpoint: str = ""
    stream_ids: tuple[int, ...] = ()
    physical_channels: tuple[int, ...] = ()
    detail: str = ""


def _hikvision_isapi_get(ip: str, path: str, username: str, password: str, timeout: float = 3.5):
    """GET one Hikvision ISAPI resource with Digest/Basic fallback.

    Returns ``(status, payload, endpoint, detail)``. No write verb is ever used.
    """
    last_status = None
    last_detail = "ISAPI não respondeu"
    for scheme in ("http", "https"):
        endpoint = f"{scheme}://{ip}{path}"
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, endpoint, username or "admin", password or "")
        handlers = [HTTPDigestAuthHandler(manager), HTTPBasicAuthHandler(manager)]
        if scheme == "https":
            handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
        opener = build_opener(*handlers)
        req = Request(endpoint, method="GET", headers={"User-Agent": "Artin-Sentinel/0.2.24"})
        try:
            with opener.open(req, timeout=timeout) as response:
                status = int(getattr(response, "status", 200) or 200)
                payload = response.read(512 * 1024)
            if 200 <= status < 300:
                return status, payload, endpoint, "ISAPI autenticada"
            last_status = status
            last_detail = f"ISAPI retornou HTTP {status}"
        except HTTPError as exc:
            last_status = int(exc.code)
            if exc.code == 401:
                last_detail = "ISAPI respondeu, mas rejeitou a credencial (HTTP 401)"
            elif exc.code == 403:
                last_detail = "ISAPI respondeu, mas o usuário não possui permissão (HTTP 403)"
            else:
                last_detail = f"ISAPI retornou HTTP {exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            last_detail = f"ISAPI {scheme.upper()} indisponível: {type(exc).__name__}"
    return last_status, b"", "", last_detail



@dataclass(frozen=True, slots=True)
class HikvisionVideoInput:
    channel_id: int
    input_port: int = 0
    enabled: bool | None = None
    name: str = ""
    video_format: str = ""
    resolution_description: str = ""


@dataclass(frozen=True, slots=True)
class HikvisionVideoInputInventory:
    ok: bool = False
    authenticated: bool = False
    status_code: int | None = None
    endpoint: str = ""
    inputs: tuple[HikvisionVideoInput, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class HikvisionProxyChannelStatus:
    channel_id: int
    protocol: str = ""
    ip_address: str = ""
    port: int = 0
    source_input_port: int = 0
    online: bool = False
    detect_result: str = ""


@dataclass(frozen=True, slots=True)
class HikvisionProxyStatusInventory:
    ok: bool = False
    authenticated: bool = False
    status_code: int | None = None
    endpoint: str = ""
    channels: tuple[HikvisionProxyChannelStatus, ...] = ()
    detail: str = ""


def _child_text(parent: ET.Element, local_name: str) -> str:
    for child in parent.iter():
        if child.tag.rsplit("}", 1)[-1].lower() == local_name.lower():
            return (child.text or "").strip()
    return ""


def probe_hikvision_isapi_video_inputs(ip: str, username: str, password: str, timeout: float = 4.0) -> HikvisionVideoInputInventory:
    """Read physical video inputs and their signal state via ISAPI GET."""
    status, payload, endpoint, detail = _hikvision_isapi_get(
        ip, "/ISAPI/System/Video/inputs/channels", username, password, timeout
    )
    if not payload:
        return HikvisionVideoInputInventory(
            ok=False, authenticated=bool(status and status != 401), status_code=status, endpoint=endpoint, detail=detail
        )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return HikvisionVideoInputInventory(
            ok=False, authenticated=True, status_code=status, endpoint=endpoint,
            detail="ISAPI Video/inputs/channels respondeu, mas o XML não pôde ser interpretado",
        )
    rows = []
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1].lower() != "videoinputchannel":
            continue
        channel_text = _child_text(elem, "id")
        if not channel_text.isdigit():
            continue
        port_text = _child_text(elem, "inputPort")
        enabled_text = _child_text(elem, "videoInputEnabled").lower()
        rows.append(HikvisionVideoInput(
            channel_id=int(channel_text),
            input_port=int(port_text) if port_text.isdigit() else 0,
            enabled=(True if enabled_text in {"true", "1", "yes"} else
                     False if enabled_text in {"false", "0", "no"} else None),
            name=_child_text(elem, "name"),
            video_format=_child_text(elem, "videoFormat"),
            resolution_description=_child_text(elem, "resDesc"),
        ))
    rows.sort(key=lambda row: row.channel_id)
    active = sum(row.enabled is not False and row.resolution_description.strip().upper() != "NO VIDEO" for row in rows)
    return HikvisionVideoInputInventory(
        ok=bool(rows), authenticated=True, status_code=status, endpoint=endpoint, inputs=tuple(rows),
        detail=(f"{len(rows)} entrada(s) física(s); {active} com sinal ou estado pendente de validação" if rows
                else "ISAPI autenticada, mas não listou entradas físicas"),
    )


def probe_hikvision_input_proxy_status(ip: str, username: str, password: str, timeout: float = 4.0) -> HikvisionProxyStatusInventory:
    """Read configured digital/IP channel status via ISAPI GET only."""
    status, payload, endpoint, detail = _hikvision_isapi_get(
        ip, "/ISAPI/ContentMgmt/InputProxy/channels/status", username, password, timeout
    )
    if not payload:
        return HikvisionProxyStatusInventory(
            ok=False, authenticated=bool(status and status != 401), status_code=status, endpoint=endpoint, detail=detail
        )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return HikvisionProxyStatusInventory(
            ok=False, authenticated=True, status_code=status, endpoint=endpoint,
            detail="ISAPI InputProxy/channels/status respondeu, mas o XML não pôde ser interpretado",
        )
    rows = []
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1].lower() != "inputproxychannelstatus":
            continue
        channel_text = _child_text(elem, "id")
        if not channel_text.isdigit():
            continue
        port_text = _child_text(elem, "managePortNo")
        source_port_text = _child_text(elem, "srcInputPort")
        online_text = _child_text(elem, "online").lower()
        rows.append(HikvisionProxyChannelStatus(
            channel_id=int(channel_text),
            protocol=_child_text(elem, "proxyProtocol"),
            ip_address=_child_text(elem, "ipAddress"),
            port=int(port_text) if port_text.isdigit() else 0,
            source_input_port=int(source_port_text) if source_port_text.isdigit() else 0,
            online=online_text in {"true", "1", "yes"},
            detect_result=_child_text(elem, "chanDetectResult"),
        ))
    rows.sort(key=lambda row: row.channel_id)
    online = sum(row.online for row in rows)
    return HikvisionProxyStatusInventory(
        ok=bool(rows), authenticated=True, status_code=status, endpoint=endpoint, channels=tuple(rows),
        detail=(f"{len(rows)} canal(is) IP configurado(s); {online} online" if rows
                else "ISAPI autenticada, sem canais IP configurados no status"),
    )

def probe_hikvision_isapi_streaming_channels(ip: str, username: str, password: str, timeout: float = 4.0) -> HikvisionStreamingInventory:
    """Read the recorder-advertised streaming channel IDs via ISAPI.

    This is deliberately preferred over guessing channels 1..N. Hikvision
    defines ``GET /ISAPI/Streaming/channels`` for this inventory and commonly
    maps 101/102 to channel 1 Main/Sub, 201/202 to channel 2, and so on.
    """
    status, payload, endpoint, detail = _hikvision_isapi_get(
        ip, "/ISAPI/Streaming/channels", username, password, timeout
    )
    if not payload:
        return HikvisionStreamingInventory(
            ok=False, authenticated=bool(status and status != 401), status_code=status,
            endpoint=endpoint, detail=detail,
        )
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return HikvisionStreamingInventory(
            ok=False, authenticated=True, status_code=status, endpoint=endpoint,
            detail="ISAPI Streaming/channels respondeu, mas o XML não pôde ser interpretado",
        )
    ids = []
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1].lower() != "streamingchannel":
            continue
        sid = ""
        for child in elem.iter():
            if child.tag.rsplit("}", 1)[-1].lower() == "id" and child.text:
                sid = child.text.strip()
                break
        if sid.isdigit():
            ids.append(int(sid))
    if not ids:
        # Some firmware returns a flatter list. Accept numeric <id> values only
        # when they resemble stream IDs, still keeping the result conservative.
        for elem in root.iter():
            if elem.tag.rsplit("}", 1)[-1].lower() == "id" and (elem.text or "").strip().isdigit():
                value = int((elem.text or "").strip())
                if value >= 1:
                    ids.append(value)
    ids = sorted(set(ids))
    physical = sorted(set((sid // 100 if sid >= 100 else sid) for sid in ids if sid > 0))
    return HikvisionStreamingInventory(
        ok=bool(ids), authenticated=True, status_code=status, endpoint=endpoint,
        stream_ids=tuple(ids), physical_channels=tuple(physical),
        detail=(f"ISAPI anunciou {len(ids)} stream(s) em {len(physical)} canal(is) físico(s)" if ids
                else "ISAPI autenticada, mas não anunciou IDs de streaming"),
    )


@dataclass(frozen=True, slots=True)
class IntelbrasChannelTitle:
    channel_id: int
    name: str = ""


@dataclass(frozen=True, slots=True)
class IntelbrasChannelInventory:
    ok: bool = False
    authenticated: bool = False
    status_code: int | None = None
    endpoint: str = ""
    channels: tuple[IntelbrasChannelTitle, ...] = ()
    detail: str = ""


def _intelbras_cgi_get(ip: str, path: str, username: str, password: str, timeout: float = 3.5):
    """GET one Intelbras/Dahua-compatible CGI resource with Digest/Basic fallback.

    The helper is intentionally read-only and never sends configManager setConfig
    or other mutating actions. Some MHDX firmwares expose only a subset of the
    Dahua-style CGI surface, so HTTP 404/400 is a normal compatibility result.
    """
    last_status = None
    last_detail = "CGI Intelbras/Dahua não respondeu"
    for scheme in ("http", "https"):
        endpoint = f"{scheme}://{ip}{path}"
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, endpoint, username or "admin", password or "")
        handlers = [HTTPDigestAuthHandler(manager), HTTPBasicAuthHandler(manager)]
        if scheme == "https":
            handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
        opener = build_opener(*handlers)
        req = Request(endpoint, method="GET", headers={"User-Agent": "Artin-Sentinel/0.2.24"})
        try:
            with opener.open(req, timeout=timeout) as response:
                status = int(getattr(response, "status", 200) or 200)
                payload = response.read(512 * 1024)
            if 200 <= status < 300:
                return status, payload, endpoint, "CGI autenticada"
            last_status = status
            last_detail = f"CGI retornou HTTP {status}"
        except HTTPError as exc:
            last_status = int(exc.code)
            if exc.code == 401:
                last_detail = "CGI respondeu, mas rejeitou a credencial (HTTP 401)"
            elif exc.code == 403:
                last_detail = "CGI respondeu, mas o usuário não possui permissão (HTTP 403)"
            else:
                last_detail = f"CGI retornou HTTP {exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            last_detail = f"CGI {scheme.upper()} indisponível: {type(exc).__name__}"
    return last_status, b"", "", last_detail


def probe_intelbras_channel_titles(ip: str, username: str, password: str, timeout: float = 3.5) -> IntelbrasChannelInventory:
    """Read ChannelTitle from compatible Intelbras/Dahua recorders.

    This is a GET-only inventory hint. Channel indices in the CGI are zero-based
    and are converted to the one-based channel numbers used by RTSP/GUI.
    """
    path = "/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"
    status, payload, endpoint, detail = _intelbras_cgi_get(ip, path, username, password, timeout)
    if not payload:
        return IntelbrasChannelInventory(
            ok=False, authenticated=bool(status and status != 401), status_code=status,
            endpoint=endpoint, detail=detail,
        )
    text = payload.decode("utf-8", "replace")
    import re as _re
    rows: dict[int, str] = {}
    for match in _re.finditer(r"(?:table\.)?ChannelTitle\[(\d+)\]\.Name=([^\r\n]*)", text, _re.I):
        idx = int(match.group(1)) + 1
        name = match.group(2).strip().replace("|", " / ")
        rows[idx] = name or f"Canal {idx:02d}"
    channels = tuple(IntelbrasChannelTitle(ch, rows[ch]) for ch in sorted(rows))
    return IntelbrasChannelInventory(
        ok=bool(channels), authenticated=True, status_code=status, endpoint=endpoint, channels=channels,
        detail=(f"CGI ChannelTitle listou {len(channels)} canal(is)" if channels
                else "CGI autenticada, mas ChannelTitle não listou canais"),
    )

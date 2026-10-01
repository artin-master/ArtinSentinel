from __future__ import annotations

"""Read-only recorder channel health monitoring.

The monitor is intentionally lighter than onboarding/channel discovery. It does
not decode video and never changes recorder configuration. Native recorder
status is preferred when a provider exposes it; existing validated RTSP routes
are used only as a bounded fallback.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Any

from .native_protocols import (
    probe_hikvision_isapi_video_inputs,
    probe_hikvision_input_proxy_status,
)
from .recorder import probe_rtsp_url_detailed


HEALTH_OK = "ok"
HEALTH_NO_SIGNAL = "no_signal"
HEALTH_OFFLINE = "offline"
HEALTH_DEGRADED = "degraded"
HEALTH_UNKNOWN = "unknown"
HEALTH_UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class ChannelHealthSample:
    channel_no: int
    state: str = HEALTH_UNKNOWN
    detail: str = ""
    source_ip: str = ""
    source_port: int = 0
    source_protocol: str = ""
    authoritative: bool = False
    media_ok: bool | None = None


def _value(row: Any, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        keys = row.keys()
        if key in keys:
            return row[key]
    except Exception:
        pass
    return getattr(row, key, default)


def _ordered_urls(channel: Any) -> list[str]:
    main = str(_value(channel, "main_rtsp_url", "") or _value(channel, "rtsp_url", "") or "")
    sub = str(_value(channel, "sub_rtsp_url", "") or "")
    last_good = str(_value(channel, "last_good_stream", "") or "")
    urls: list[str] = []
    if last_good == "sub" and sub:
        urls.append(sub)
    elif last_good == "main" and main:
        urls.append(main)
    for url in (main, sub):
        if url and url not in urls:
            urls.append(url)
    return urls


def _fallback_rtsp_sample(channel: Any, username: str, password: str) -> ChannelHealthSample:
    channel_no = int(_value(channel, "channel_no", 0) or 0)
    urls = _ordered_urls(channel)
    if not urls:
        return ChannelHealthSample(
            channel_no, HEALTH_UNVERIFIED, "Sem rota RTSP conhecida para verificação", authoritative=False, media_ok=None
        )

    details: list[str] = []
    # Health checks intentionally test at most two already-known routes and do
    # not enumerate new paths. This keeps the 30 s monitor bounded.
    for url in urls[:2]:
        report = probe_rtsp_url_detailed(url, username, password, timeout=1.0, use_ffprobe=False)
        details.append(report.safe_summary() or report.detail)
        if report.ok:
            return ChannelHealthSample(
                channel_no,
                HEALTH_OK,
                "RTSP validado pela rota conhecida",
                authoritative=False,
                media_ok=True,
            )

    tail = next((d for d in reversed(details) if d), "")
    return ChannelHealthSample(
        channel_no,
        HEALTH_UNVERIFIED,
        "RTSP não confirmou a rota conhecida; sinal da câmera não verificado"
        + (f" • {tail}" if tail else ""),
        authoritative=False,
        media_ok=None,
    )


def _hikvision_samples(ip: str, username: str, password: str, channels: list[Any]) -> dict[int, ChannelHealthSample]:
    out: dict[int, ChannelHealthSample] = {}
    physical = probe_hikvision_isapi_video_inputs(ip, username, password, timeout=3.5)
    proxy = probe_hikvision_input_proxy_status(ip, username, password, timeout=3.5)

    if physical.authenticated:
        for row in physical.inputs:
            channel_no = int(row.channel_id)
            has_signal = bool(row.enabled) and str(row.resolution_description or "").strip().upper() != "NO VIDEO"
            state = HEALTH_OK if has_signal else HEALTH_NO_SIGNAL
            detail_parts = ["ISAPI entrada física"]
            if row.resolution_description:
                detail_parts.append(str(row.resolution_description))
            detail_parts.append("sinal presente" if has_signal else "sem sinal")
            out[channel_no] = ChannelHealthSample(
                channel_no,
                state,
                " • ".join(detail_parts),
                authoritative=True,
                media_ok=True if has_signal else False,
            )

    if proxy.authenticated:
        for row in proxy.channels:
            channel_no = int(row.channel_id)
            state = HEALTH_OK if row.online else HEALTH_OFFLINE
            endpoint = str(row.ip_address or "")
            detail_parts = ["ISAPI canal IP", "online" if row.online else "offline"]
            if row.detect_result:
                detail_parts.append(str(row.detect_result))
            out[channel_no] = ChannelHealthSample(
                channel_no,
                state,
                " • ".join(detail_parts),
                source_ip=endpoint,
                source_port=int(row.port or 0),
                source_protocol=str(row.protocol or ""),
                authoritative=True,
                media_ok=True if row.online else False,
            )

    # When ISAPI does not describe a saved channel, keep compatibility with
    # other Hikvision firmware by checking only its already-known RTSP route.
    for channel in channels:
        no = int(_value(channel, "channel_no", 0) or 0)
        if no and no not in out:
            out[no] = _fallback_rtsp_sample(channel, username, password)
    return out


def probe_recorder_channel_health(
    provider: str,
    ip: str,
    username: str,
    password: str,
    channels: Iterable[Any],
) -> list[ChannelHealthSample]:
    """Return current health for saved recorder channels using read-only probes.

    Native status is currently authoritative for Hikvision. Intelbras/Dahua and
    generic providers use only the last-known RTSP routes; this avoids changing
    the recorder or re-running the slower discovery routine every 30 seconds.
    """
    rows = list(channels)
    provider_key = str(provider or "").strip().lower()
    if provider_key in {"hikvision", "hikvision-isapi"}:
        result = _hikvision_samples(ip, username, password, rows)
        return [result[key] for key in sorted(result)]

    return [
        _fallback_rtsp_sample(channel, username, password)
        for channel in rows
        if int(_value(channel, "channel_no", 0) or 0) > 0
    ]

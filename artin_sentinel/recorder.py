from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event
from urllib.parse import quote, urlparse, urlunparse

from . import __version__
from .live import authenticated_rtsp_url, ffmpeg_rtsp_timeout_args, probe_rtsp_media_capabilities
from .native_protocols import (
    probe_hikvision_isapi_device_info,
    probe_hikvision_isapi_streaming_channels,
    probe_hikvision_isapi_video_inputs,
    probe_hikvision_input_proxy_status,
    probe_hikvision_input_proxy_channels,
    probe_intelbras_channel_titles,
)


@dataclass(slots=True)
class RecorderChannel:
    channel: int
    name: str
    rtsp_url: str
    available: bool
    status_code: int | None = None
    detail: str = ""
    source_name: str = ""
    main_rtsp_url: str = ""
    sub_rtsp_url: str = ""
    route_kind: str = "via_recorder"
    channel_kind: str = "unknown"
    audio_mode: str = "unknown"
    audio_codec: str = ""
    audio_sample_rate: int = 0
    audio_channels: int = 0
    audio_detail: str = ""


class RecorderScanResult(list[RecorderChannel]):
    """Channel inventory with an explicit marker for incomplete RTSP validation."""

    def __init__(self, channels=(), *, partial: bool = False, untested: int = 0, identity=None, notice="", preserve_existing=False):
        super().__init__(channels)
        self.partial = bool(partial)
        self.untested = int(untested)
        self.identity = identity
        self.notice = notice
        self.preserve_existing = bool(preserve_existing)


def channels_for_live_view(channels, kind: str):
    """NVR inventory positions require a verified stream before opening all."""
    ready = [channel for channel in channels if bool(channel["available"])]
    if kind in {"nvr", "camera"}:
        return ready
    if ready:
        return ready
    def explicitly_no_signal(channel):
        try:
            kind, detail = channel["channel_kind"], str(channel["detail"] or "").lower()
        except (KeyError, IndexError, TypeError):
            return False
        return kind == "analog" and ("no video" in detail or "sem sinal" in detail)
    # Keep legacy unknown DVR rows available for a manual opening, but never
    # open a full black mosaic for physical inputs explicitly without signal.
    return [channel for channel in channels if not explicitly_no_signal(channel)]


def _audio_fields_for_urls(urls, username: str, password: str) -> dict:
    """Probe Main/Sub media tracks after RTSP validation, bounded and read-only."""
    seen = []
    details = []
    any_media = False
    for url in urls:
        if not url or url in seen:
            continue
        seen.append(url)
        probe = probe_rtsp_media_capabilities(url, username, password, timeout=4.0)
        details.append(probe.detail)
        any_media = any_media or probe.ok
        if probe.has_audio:
            return {
                "audio_mode": "listen",
                "audio_codec": probe.audio_codec,
                "audio_sample_rate": probe.audio_sample_rate,
                "audio_channels": probe.audio_channels,
                "audio_detail": " • ".join(d for d in details if d),
            }
    return {
        "audio_mode": "none" if any_media else "unknown",
        "audio_codec": "",
        "audio_sample_rate": 0,
        "audio_channels": 0,
        "audio_detail": " • ".join(d for d in details if d),
    }


@dataclass(slots=True)
class RtspProbeReport:
    ok: bool
    status_code: int | None
    detail: str
    first_status: int | None = None
    authenticated_status: int | None = None
    auth_scheme: str = ""
    realm: str = ""
    algorithm: str = ""
    qop: str = ""
    strategy: str = ""
    ffprobe_used: bool = False
    ffprobe_ok: bool = False

    def safe_summary(self) -> str:
        parts: list[str] = []
        if self.first_status is not None:
            parts.append(f"primeira resposta {self.first_status}")
        if self.auth_scheme:
            auth = self.auth_scheme
            extras = []
            if self.realm:
                extras.append(f"realm={self.realm!r}")
            if self.algorithm:
                extras.append(f"algoritmo={self.algorithm}")
            if self.qop:
                extras.append(f"qop={self.qop}")
            if extras:
                auth += " (" + ", ".join(extras) + ")"
            parts.append(auth)
        if self.authenticated_status is not None:
            parts.append(f"resposta autenticada {self.authenticated_status}")
        if self.strategy:
            parts.append(f"estratégia={self.strategy}")
        if self.ffprobe_used:
            parts.append("ffprobe=" + ("OK" if self.ffprobe_ok else "não confirmou"))
        return "; ".join(parts) or self.detail


class ChannelScanCancelled(RuntimeError):
    """Cooperative cancellation used by the recorder onboarding worker."""


class RtspAuthenticationError(RuntimeError):
    """RTSP answered, but an authenticated session could not be confirmed."""


class RtspCompatibilityError(RuntimeError):
    """RTSP is reachable, but the recorder URL/auth profile is not confirmed."""


def _parse_digest_header(value: str) -> dict[str, str]:
    value = value.strip()
    if value.lower().startswith("digest "):
        value = value[7:]
    out: dict[str, str] = {}
    for match in re.finditer(r'(\w+)=((?:"(?:[^"\\]|\\.)*")|[^,]+)', value):
        key, raw = match.groups()
        raw = raw.strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        out[key.lower()] = raw
    return out


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _digest_authorization(
    challenge: str,
    username: str,
    password: str,
    method: str,
    digest_uri: str,
    *,
    force_legacy_no_qop: bool = False,
) -> str:
    """Build a Digest Authorization header.

    Some older recorder firmwares are picky about details that desktop players
    tolerate. In particular, they may reject an `algorithm=MD5` token when the
    challenge did not advertise an algorithm, or may advertise qop but only
    accept RFC-2069 style Digest. We preserve the challenge as closely as
    possible and expose a bounded legacy retry for compatibility testing.
    """
    p = _parse_digest_header(challenge)
    realm = p.get("realm", "")
    nonce = p.get("nonce", "")
    qop_raw = p.get("qop", "")
    algorithm_raw = p.get("algorithm", "")
    algorithm = (algorithm_raw or "MD5").upper()
    if algorithm not in ("MD5", "MD5-SESS"):
        raise ValueError(f"Digest algorithm não suportado: {algorithm}")
    if not nonce:
        raise ValueError("Desafio Digest sem nonce")

    ha1 = _md5(f"{username}:{realm}:{password}")
    cnonce = os.urandom(8).hex()
    if algorithm == "MD5-SESS":
        ha1 = _md5(f"{ha1}:{nonce}:{cnonce}")
    ha2 = _md5(f"{method}:{digest_uri}")

    chosen_qop = ""
    if qop_raw and not force_legacy_no_qop:
        opts = [x.strip().lower() for x in qop_raw.split(",")]
        if "auth" in opts:
            chosen_qop = "auth"
    if chosen_qop:
        nc = "00000001"
        response = _md5(f"{ha1}:{nonce}:{nc}:{cnonce}:{chosen_qop}:{ha2}")
    else:
        response = _md5(f"{ha1}:{nonce}:{ha2}")

    parts = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{digest_uri}"',
        f'response="{response}"',
    ]
    # Do not invent the algorithm token when the recorder did not send it.
    if algorithm_raw:
        parts.append(f"algorithm={algorithm}")
    opaque = p.get("opaque")
    if opaque:
        parts.append(f'opaque="{opaque}"')
    if chosen_qop:
        parts.extend([f"qop={chosen_qop}", "nc=00000001", f'cnonce="{cnonce}"'])
    return "Digest " + ", ".join(parts)


def _response_complete(raw: bytes) -> bool:
    marker = raw.find(b"\r\n\r\n")
    if marker < 0:
        return False
    header = raw[:marker].decode("latin1", "replace")
    body_len = len(raw) - marker - 4
    match = re.search(r"(?im)^Content-Length\s*:\s*(\d+)\s*$", header)
    if match:
        return body_len >= int(match.group(1))
    return True


def _rtsp_request(
    host: str,
    port: int,
    target: str,
    method: str = "DESCRIBE",
    authorization: str = "",
    timeout: float = 1.25,
    cseq: int = 1,
) -> tuple[int | None, dict[str, str], str]:
    lines = [
        f"{method} {target} RTSP/1.0",
        f"CSeq: {int(cseq)}",
        f"User-Agent: Artin-Sentinel/{__version__}",
        "Accept: application/sdp",
    ]
    if authorization:
        lines.append(f"Authorization: {authorization}")
    payload = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload)
            raw = b""
            while len(raw) < 65536:
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    break
                if not data:
                    break
                raw += data
                if _response_complete(raw):
                    break
    except OSError as exc:
        return None, {}, str(exc)

    text = raw.decode("latin1", "replace")
    head, _, body = text.partition("\r\n\r\n")
    first = head.splitlines()[0] if head else ""
    match = re.match(r"RTSP/\d\.\d\s+(\d+)", first)
    code = int(match.group(1)) if match else None
    headers: dict[str, str] = {}
    for line in head.splitlines()[1:]:
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            if key in headers and key == "www-authenticate":
                headers[key] += ", " + val
            else:
                headers[key] = val
    return code, headers, body


def _challenge_scheme(challenge: str) -> str:
    low = challenge.strip().lower()
    if low.startswith("digest") or "digest realm=" in low:
        return "Digest"
    if low.startswith("basic") or "basic realm=" in low:
        return "Basic"
    return ""


def _digest_challenge_only(challenge: str) -> str:
    # When a server emits more than one WWW-Authenticate line our tiny header
    # collector may join them. Prefer the Digest portion if present.
    pos = challenge.lower().find("digest ")
    if pos >= 0:
        return challenge[pos:]
    return challenge


def _basic_challenge_only(challenge: str) -> str:
    pos = challenge.lower().find("basic ")
    if pos >= 0:
        return challenge[pos:]
    return challenge


def _path_query(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return path


@lru_cache(maxsize=1)
def ffprobe_rtsp_timeout_args() -> tuple[str, ...]:
    """Return an RTSP timeout option supported by the local ffprobe build.

    Fedora/FFmpeg builds used in field tests rejected ``-rw_timeout`` for RTSP.
    Query the RTSP demuxer and use its own option when available.  If the help
    query is unavailable, prefer ``-timeout`` rather than the generic option.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return ()
    try:
        cp = subprocess.run(
            [ffprobe, "-hide_banner", "-h", "demuxer=rtsp"],
            capture_output=True, text=True, timeout=2.0, check=False,
        )
        help_text = f"{cp.stdout}\n{cp.stderr}"
    except (OSError, subprocess.TimeoutExpired):
        help_text = ""
    if re.search(r"(?m)^\s*-timeout\s", help_text):
        return ("-timeout", "5000000")
    if re.search(r"(?m)^\s*-stimeout\s", help_text):
        return ("-stimeout", "5000000")
    if not help_text:
        return ("-timeout", "5000000")
    return ()


def materialize_rtsp_template(url: str, username: str, password: str) -> str:
    """Fill credential placeholders without ever persisting the actual secret."""
    return (url or "").replace("{username}", quote(username or "", safe="")).replace("{password}", quote(password or "", safe=""))


def _ffprobe_probe(url: str, username: str, password: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Use ffprobe as an independent RTSP implementation when available.

    Direct-camera field tests showed that some OEM cameras answer RTSP but only
    deliver media over one transport. Try TCP first (preferred for VMS use) and
    fall back to UDP when TCP does not produce a decodable stream. Authentication
    or 404 failures are not retried with another transport because transport does
    not fix credentials or an invalid path.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return False, "ffprobe indisponível"
    url = materialize_rtsp_template(url, username, password)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 554
    userinfo = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    netloc = f"{userinfo}{host}:{port}"
    auth_url = urlunparse((parsed.scheme or "rtsp", netloc, parsed.path, "", parsed.query, ""))
    timeout_args = list(ffprobe_rtsp_timeout_args())
    last_detail = "ffprobe não confirmou o stream"
    for transport in ("tcp", "udp"):
        cmd = [
            ffprobe,
            "-v", "error",
            "-rtsp_transport", transport,
            *timeout_args,
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height",
            "-of", "json",
            auth_url,
        ]
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1.5, check=False)
        except (subprocess.TimeoutExpired, OSError):
            last_detail = f"ffprobe sem confirmação via {transport.upper()} (timeout/execução)"
            continue
        if cp.returncode == 0:
            try:
                payload = json.loads(cp.stdout or "{}")
            except json.JSONDecodeError:
                payload = {}
            streams = payload.get("streams") or []
            if streams:
                first = streams[0]
                codec = first.get("codec_name") or "vídeo"
                width = first.get("width")
                height = first.get("height")
                suffix = f" {width}x{height}" if width and height else ""
                return True, f"ffprobe confirmou {codec}{suffix} via {transport.upper()}"
            return True, f"ffprobe confirmou o endpoint RTSP via {transport.upper()}"
        err = (cp.stderr or "").lower()
        if "401" in err or "unauthorized" in err:
            return False, "ffprobe recebeu 401/Unauthorized"
        if "404" in err or "not found" in err:
            return False, "ffprobe indicou URL/stream inexistente"
        if "connection refused" in err:
            return False, "ffprobe: conexão recusada"
        if "461" in err or "unsupported transport" in err:
            last_detail = f"ffprobe: transporte {transport.upper()} não aceito"
            continue
        last_detail = f"ffprobe não confirmou o stream via {transport.upper()}"
    return False, last_detail


def validate_rtsp_media(
    url: str,
    username: str = "",
    password: str = "",
    timeout: float = 5.0,
) -> tuple[bool, str]:
    """Confirm that an RTSP URL actually exposes a decodable video stream.

    For direct IP cameras a successful RTSP DESCRIBE is not sufficient: several
    OEM firmwares answer generic paths with an SDP even when the requested
    profile is not usable.  Prefer ffprobe/libavformat and fall back to the
    internal DESCRIBE client only when ffprobe is unavailable.
    """
    if shutil.which("ffprobe"):
        return _ffprobe_probe(url, username, password, timeout=timeout)
    report = probe_rtsp_url_detailed(url, username, password, timeout=min(timeout, 1.5), use_ffprobe=False)
    return report.ok, report.detail


def confirm_nvr_video_frame(url: str, username: str, password: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Check that a recorder RTSP endpoint actually yields one decoded frame.

    Some NVRs return a valid SDP for a configured position without forwarding
    any camera video. Use the same FFmpeg/TCP transport as Live View and never
    expose the authenticated URL in diagnostics or store its credentials.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg ausente; não foi possível confirmar quadro de vídeo"
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", *ffmpeg_rtsp_timeout_args(),
        "-i", authenticated_rtsp_url(url, username, password),
        "-map", "0:v:0", "-an", "-sn", "-dn", "-frames:v", "1",
        "-vf", "scale=16:16", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1",
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return False, "RTSP respondeu, mas não entregou quadro de vídeo no prazo"
    except OSError:
        return False, "não foi possível executar FFmpeg para validar vídeo"
    if result.returncode == 0 and len(result.stdout or b"") >= 256:
        return True, "quadro de vídeo decodificado via TCP"
    error = (result.stderr or b"").decode("utf-8", "replace").lower()
    if "401" in error or "unauthorized" in error:
        reason = "autenticação RTSP não aceita pelo FFmpeg"
    elif "404" in error or "not found" in error:
        reason = "stream RTSP não existe para esta posição"
    elif "461" in error or "unsupported transport" in error:
        reason = "transporte RTSP TCP não aceito"
    else:
        reason = "RTSP respondeu, mas não entregou quadro de vídeo decodificável"
    return False, reason


def probe_rtsp_url_detailed(
    url: str,
    username: str = "",
    password: str = "",
    timeout: float = 1.25,
    use_ffprobe: bool = True,
) -> RtspProbeReport:
    url = materialize_rtsp_template(url, username, password)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 554
    target = url
    code, headers, body = _rtsp_request(host, port, target, timeout=timeout, cseq=1)
    if code == 200:
        return RtspProbeReport(True, 200, _sdp_summary(body), first_status=200, strategy="sem autenticação")
    if code is None:
        return RtspProbeReport(False, None, "RTSP sem resposta", first_status=None)

    challenge = headers.get("www-authenticate", "")
    scheme = _challenge_scheme(challenge)
    report = RtspProbeReport(False, code, f"RTSP {code}", first_status=code, auth_scheme=scheme)

    if code == 401 and username and scheme:
        if scheme == "Digest":
            challenge = _digest_challenge_only(challenge)
            parsed_challenge = _parse_digest_header(challenge)
            report.realm = parsed_challenge.get("realm", "")
            report.algorithm = (parsed_challenge.get("algorithm") or "MD5").upper()
            report.qop = parsed_challenge.get("qop", "")
            variants = [
                ("digest-uri absoluto", target, False),
                ("digest-uri caminho", _path_query(url), False),
            ]
            if parsed_challenge.get("qop"):
                variants.extend([
                    ("digest legado sem qop / uri absoluto", target, True),
                    ("digest legado sem qop / uri caminho", _path_query(url), True),
                ])
            last_code = code
            for idx, (strategy, digest_uri, legacy_no_qop) in enumerate(variants, start=2):
                try:
                    auth = _digest_authorization(
                        challenge,
                        username,
                        password,
                        "DESCRIBE",
                        digest_uri,
                        force_legacy_no_qop=legacy_no_qop,
                    )
                except Exception as exc:
                    report.detail = f"Falha ao montar Digest: {type(exc).__name__}"
                    break
                code2, _headers2, body2 = _rtsp_request(
                    host, port, target, authorization=auth, timeout=timeout, cseq=idx
                )
                last_code = code2
                if code2 == 200:
                    report.ok = True
                    report.status_code = 200
                    report.authenticated_status = 200
                    report.strategy = strategy
                    report.detail = _sdp_summary(body2)
                    return report
                # 404/400 after auth is significant: credentials may have been
                # accepted and the URL/profile is wrong. Preserve that distinction.
                if code2 in (400, 404, 454):
                    report.authenticated_status = code2
                    report.strategy = strategy
                    report.detail = f"RTSP {code2} após autenticação; URL/perfil pode não existir"
                    break
            report.authenticated_status = last_code
            if not report.strategy:
                report.strategy = "Digest interno"
        elif scheme == "Basic":
            _ = _basic_challenge_only(challenge)
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            auth = f"Basic {token}"
            code2, _headers2, body2 = _rtsp_request(
                host, port, target, authorization=auth, timeout=timeout, cseq=2
            )
            report.authenticated_status = code2
            report.strategy = "Basic"
            if code2 == 200:
                report.ok = True
                report.status_code = 200
                report.detail = _sdp_summary(body2)
                return report
            report.detail = f"RTSP {code2 or 'sem resposta'} após Basic"
    elif code == 401:
        report.detail = "RTSP exige autenticação"
    else:
        report.detail = f"RTSP {code}"

    if use_ffprobe and username and code in (400, 401, 403, 404, 454):
        report.ffprobe_used = shutil.which("ffprobe") is not None
        if report.ffprobe_used:
            ff_ok, ff_detail = _ffprobe_probe(url, username, password)
            report.ffprobe_ok = ff_ok
            if ff_ok:
                report.ok = True
                report.status_code = 200
                report.strategy = "ffprobe/libavformat"
                report.detail = ff_detail
                return report
            report.detail = (report.detail + " • " + ff_detail).strip(" •")
    return report


def probe_rtsp_url(
    url: str,
    username: str = "",
    password: str = "",
    timeout: float = 1.25,
) -> tuple[bool, int | None, str]:
    report = probe_rtsp_url_detailed(url, username, password, timeout=timeout)
    return report.ok, report.status_code, report.detail


def _sdp_summary(body: str) -> str:
    codecs = []
    for line in body.splitlines():
        if line.startswith("a=rtpmap:") and "/" in line:
            codec = line.split(None, 1)[-1].split("/", 1)[0].strip()
            if codec and codec not in codecs:
                codecs.append(codec)
    return "SDP OK" + (" • " + ", ".join(codecs[:3]) if codecs else "")


def intelbras_channel_url(ip: str, channel: int, subtype: int = 0, port: int = 554) -> str:
    return f"rtsp://{ip}:{port}/cam/realmonitor?channel={int(channel)}&subtype={int(subtype)}"


def intelbras_channel_url_variants(ip: str, channel: int, subtype: int = 0, port: int = 554) -> list[str]:
    """Bounded URL variants used only for compatibility diagnostics.

    The first URL is Intelbras' documented format. The alternate query order is
    included because some OEM-derived firmwares have historically parsed query
    strings rigidly even though they should be equivalent.
    """
    base = f"rtsp://{ip}:{port}/cam/realmonitor"
    return [
        f"{base}?channel={int(channel)}&subtype={int(subtype)}",
        f"{base}?subtype={int(subtype)}&channel={int(channel)}",
    ]


def _check_cancel(cancel_event: Event | None):
    if cancel_event is not None and cancel_event.is_set():
        raise ChannelScanCancelled("Leitura de canais cancelada pelo usuário.")


def _select_stream_profile(
    ip: str,
    username: str,
    password: str,
    cancel_event: Event | None,
    port: int = 554,
) -> tuple[int, int, str, str]:
    """Validate the documented MHDX/Intelbras RTSP profile before full scan."""
    saw_response = False
    auth_reports: list[str] = []
    compatibility_reports: list[str] = []
    # Preserve the proven MHDX analogue mapping first. Field validation on
    # 0.2.23 showed that probing the extra IP channel before the four legacy
    # inputs can disturb RTSP validation on some firmware revisions. The fifth
    # IP/proxy channel is therefore an extension, never a replacement for the
    # established channels 1..4.
    for channel in (1, 2, 3, 4, 5):
        for subtype in (0, 1):
            for url in intelbras_channel_url_variants(ip, channel, subtype=subtype, port=port):
                _check_cancel(cancel_event)
                report = probe_rtsp_url_detailed(url, username, password)
                if report.first_status is not None:
                    saw_response = True
                summary = report.safe_summary()
                if report.ok:
                    return channel, subtype, report.detail, url
                if report.first_status == 401:
                    auth_reports.append(summary)
                elif report.first_status is not None:
                    compatibility_reports.append(summary)

    if auth_reports:
        # Do not label the password as wrong: the same credentials may work in
        # the vendor client while our Digest dialect still needs adaptation.
        sample = auth_reports[-1]
        raise RtspAuthenticationError(
            "O gravador respondeu ao RTSP e solicitou autenticação, mas o Sentinel ainda não confirmou uma sessão autenticada. "
            "Isso não confirma senha incorreta. Pode ser a conta, a permissão RTSP ou uma particularidade Digest deste firmware. "
            f"Diagnóstico seguro: {sample}."
        )
    if not saw_response:
        raise ConnectionError(f"Não foi possível conversar com o serviço RTSP do gravador na porta {port}.")
    sample = compatibility_reports[-1] if compatibility_reports else "sem detalhe adicional"
    raise RtspCompatibilityError(
        "O RTSP respondeu, porém nenhum dos perfis de URL Intelbras testados foi confirmado. "
        f"Diagnóstico seguro: {sample}."
    )


def scan_intelbras_channels(
    ip: str,
    username: str,
    password: str,
    max_channels: int = 32,
    progress=None,
    cancel_event: Event | None = None,
    max_seconds: float | None = None,
    rtsp_port: int = 554,
    http_port: int = 80,
    channel_layout: str = "mhdx1004",
) -> list[RecorderChannel]:
    """Read-only channel availability scan for Intelbras/Dahua-style recorders.

    The built-in client sends RTSP DESCRIBE only. If the recorder's Digest
    dialect is not accepted and ffprobe is installed, libavformat is used as an
    independent read-only compatibility check. No recorder setting is changed
    and credentials are never persisted by this module.
    """
    if max_seconds is None:
        max_seconds = min(150.0, max(35.0, 25.0 + int(max_channels) * 4.0))
    started = time.monotonic()
    if progress:
        progress("Lendo inventário Intelbras/Dahua e validando RTSP do gravador…")

    # Some MHDX firmwares expose the channel list through the Dahua-compatible
    # ChannelTitle CGI even when an input currently has no video. This is GET
    # only and allows the fifth IP channel to remain visible as inventory.
    cgi_inventory = probe_intelbras_channel_titles(
        f"{ip}:{http_port}" if http_port != 80 else ip, username, password, timeout=3.0
    )
    cgi_names = {row.channel_id: row.name for row in cgi_inventory.channels}
    if progress and cgi_inventory.ok:
        progress(f"{cgi_inventory.detail}. Validando mídia RTSP…")

    preferred_subtype = 0
    detail = ""
    confirmed_url = ""
    try:
        _seed_channel, preferred_subtype, detail, confirmed_url = _select_stream_profile(
            ip, username, password, cancel_event, port=rtsp_port
        )
    except (RtspCompatibilityError, ConnectionError, RtspAuthenticationError) as exc:
        # If the read-only CGI already authenticated, preserve inventory even
        # when no RTSP media is currently available or the RTSP Digest dialect
        # differs. A real credential failure is still reported when CGI could
        # not authenticate either.
        if not cgi_inventory.authenticated:
            if isinstance(exc, RtspAuthenticationError) and getattr(cgi_inventory, "status_code", None) == 401:
                raise RtspAuthenticationError(
                    f"{exc} A consulta HTTP ao gravador também respondeu 401; "
                    "confira a conta e as permissões deste equipamento separadamente."
                ) from exc
            raise
        detail = "CGI autenticada; RTSP ainda sem mídia confirmada"
    if progress:
        if confirmed_url:
            stream_name = "principal" if preferred_subtype == 0 else "secundário"
            engine = "ffprobe" if detail.startswith("ffprobe") else "RTSP interno"
            progress(f"RTSP confirmado ({stream_name}, {engine}). Analisando canais…")
        else:
            progress("Inventário autenticado; verificando mídia dos canais, incluindo o canal IP extra…")

    channels: list[RecorderChannel] = []

    def kind_for_channel(ch: int) -> str:
        if channel_layout == "nvr":
            return "ip"
        if channel_layout == "mhdx1004":
            return "analog" if ch <= 4 else "ip"
        return "unknown"

    def one(ch: int) -> RecorderChannel:
        _check_cancel(cancel_event)
        # Keep the URL shape that was confirmed in preflight (query order),
        # replacing only channel and subtype.
        # Hybrid recorders can expose extra IP channels with firmware quirks that
        # do not necessarily use the same query order as the analogue seed. Probe
        # both documented/legacy query orders for main and sub independently.
        main_variants = intelbras_channel_url_variants(ip, ch, subtype=0, port=rtsp_port)
        sub_variants = intelbras_channel_url_variants(ip, ch, subtype=1, port=rtsp_port)
        source_name = cgi_names.get(ch) or f"Canal {ch:02d}"
        reports = []
        frame_failures = []
        main_ok = ""
        sub_ok = ""
        preferred_order = (main_variants, sub_variants) if preferred_subtype == 0 else (sub_variants, main_variants)
        for variants in preferred_order:
            for candidate in variants:
                report = probe_rtsp_url_detailed(candidate, username, password)
                reports.append((candidate, report))
                if report.ok:
                    if channel_layout == "nvr":
                        frame_ok, frame_detail = confirm_nvr_video_frame(candidate, username, password)
                        if not frame_ok:
                            frame_failures.append(frame_detail)
                            # The URL responded with SDP, but the same stream
                            # query in reverse order will not create camera media.
                            break
                        report.detail = f"{report.detail} • {frame_detail}"
                    if "subtype=0" in candidate:
                        main_ok = candidate
                    else:
                        sub_ok = candidate
                    break
        # If one profile worked, opportunistically validate the other profile so
        # Auto/Main/Sub can be switched later without another recorder scan.
        if main_ok and not sub_ok:
            for candidate in sub_variants:
                report = probe_rtsp_url_detailed(candidate, username, password)
                reports.append((candidate, report))
                if report.ok:
                    if channel_layout == "nvr":
                        frame_ok, frame_detail = confirm_nvr_video_frame(candidate, username, password)
                        if not frame_ok:
                            frame_failures.append(frame_detail)
                            break
                        report.detail = f"{report.detail} • {frame_detail}"
                    sub_ok = candidate
                    break
        if sub_ok and not main_ok:
            for candidate in main_variants:
                report = probe_rtsp_url_detailed(candidate, username, password)
                reports.append((candidate, report))
                if report.ok:
                    if channel_layout == "nvr":
                        frame_ok, frame_detail = confirm_nvr_video_frame(candidate, username, password)
                        if not frame_ok:
                            frame_failures.append(frame_detail)
                            break
                        report.detail = f"{report.detail} • {frame_detail}"
                    main_ok = candidate
                    break
        if main_ok or sub_ok:
            chosen = main_ok if preferred_subtype == 0 and main_ok else sub_ok or main_ok
            ok_report = next((r for u, r in reports if u == chosen), None)
            return RecorderChannel(
                ch, source_name, chosen, True,
                ok_report.status_code if ok_report else 200,
                (ok_report.detail if ok_report else "RTSP confirmado"),
                source_name=source_name, main_rtsp_url=main_ok, sub_rtsp_url=sub_ok,
                channel_kind=kind_for_channel(ch),
                **_audio_fields_for_urls((chosen, main_ok, sub_ok), username, password),
            )
        last_report = reports[-1][1] if reports else None
        detail_text = (last_report.safe_summary() or last_report.detail) if last_report else "sem resposta RTSP"
        if frame_failures:
            detail_text += " • " + frame_failures[0]
        if ch in cgi_names:
            detail_text = f"inventariado via CGI • {detail_text}"
        elif channel_layout == "mhdx1004" and ch == 5 and max_channels >= 5:
            detail_text = f"canal IP/proxy via gravador • {detail_text}"
        return RecorderChannel(
            ch, source_name, main_variants[0], False,
            last_report.status_code if last_report else None, detail_text,
            source_name=source_name, main_rtsp_url=main_variants[0], sub_rtsp_url=sub_variants[0],
            channel_kind=kind_for_channel(ch),
        )

    # Keep the known-good MHDX channels 1..4 in the same first-wave order as
    # 0.2.22. The fifth channel is an IP/proxy route exposed by the recorder
    # and is scanned afterwards. This prevents the new hybrid path from
    # regressing an analogue channel that was already homologated.
    ordered = []
    legacy_first = [ch for ch in (1, 2, 3, 4) if ch <= int(max_channels)] if channel_layout == "mhdx1004" else []
    for ch in [*legacy_first, *sorted(cgi_names), *range(1, max_channels + 1)]:
        if 1 <= int(ch) <= int(max_channels) and int(ch) not in ordered:
            ordered.append(int(ch))
    done = 0
    timed_out = False

    def run_batch(batch: list[int], workers: int) -> None:
        nonlocal done, timed_out
        if not batch or timed_out:
            return
        remaining = max_seconds - (time.monotonic() - started)
        if remaining <= 0:
            timed_out = True
            return
        with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(batch))), thread_name_prefix="sentinel-channels") as pool:
            futures = {pool.submit(one, ch): ch for ch in batch}
            try:
                for fut in as_completed(futures, timeout=remaining):
                    _check_cancel(cancel_event)
                    if time.monotonic() - started > max_seconds:
                        timed_out = True
                        break
                    result = fut.result()
                    channels.append(result)
                    done += 1
                    if progress and (result.available or done % 4 == 0 or done == len(ordered)):
                        suffix = f" • canal {result.channel} disponível" if result.available else ""
                        progress(f"Canais analisados: {done}/{len(ordered)}{suffix}")
            except TimeoutError:
                timed_out = True
            finally:
                if timed_out or (cancel_event is not None and cancel_event.is_set()):
                    for fut in futures:
                        fut.cancel()

    # Phase 1 is intentionally isolated: no hybrid/IP probe is started until
    # the four legacy analogue positions have completed. This turns the old
    # 'submission order' into a real isolation boundary and prevents channel 5
    # probing from perturbing the already field-proven 1..4 mapping.
    legacy_batch = [ch for ch in ordered if ch in {1, 2, 3, 4}]
    hybrid_batch = [ch for ch in ordered if ch not in {1, 2, 3, 4}]
    run_batch(legacy_batch, 4)
    if channel_layout == "mhdx1004":
        run_batch(hybrid_batch, 2)
    elif channel_layout == "nvr":
        run_batch(hybrid_batch, 2)
    else:
        run_batch(hybrid_batch, 4)

    _check_cancel(cancel_event)
    scanned = {row.channel for row in channels}
    untested = 0
    if timed_out:
        # The AKDB/model inventory is useful even if slower RTSP verification
        # expires. These entries are never advertised as live video.
        for ch in ordered:
            if ch in scanned:
                continue
            untested += 1
            main_url = intelbras_channel_url_variants(ip, ch, subtype=0, port=rtsp_port)[0]
            sub_url = intelbras_channel_url_variants(ip, ch, subtype=1, port=rtsp_port)[0]
            name = cgi_names.get(ch) or f"Canal {ch:02d}"
            channels.append(RecorderChannel(
                ch, name, main_url, False, None,
                "Posição do modelo AKDB; RTSP ainda não testado (tempo limite)",
                source_name=name, main_rtsp_url=main_url, sub_rtsp_url=sub_url,
                channel_kind=kind_for_channel(ch),
            ))
        if progress:
            progress(f"Tempo de validação esgotado; {untested} canal(is) pendente(s), inventário preservado.")
    channels.sort(key=lambda c: c.channel)
    return RecorderScanResult(channels, partial=timed_out, untested=untested)

# ---------------------------------------------------------------------------
# Hikvision-compatible recorder support (read-only)
# ---------------------------------------------------------------------------

def hikvision_channel_url(ip: str, channel: int, subtype: int = 0, port: int = 554) -> str:
    """Return the standard Hikvision RTSP path.

    channel=1 => 101 main / 102 sub, channel=2 => 201 / 202, etc.
    """
    suffix = 1 if int(subtype) == 0 else 2
    logical = int(channel) * 100 + suffix
    return f"rtsp://{ip}:{port}/Streaming/Channels/{logical}"


def scan_hikvision_channels(
    ip: str,
    username: str,
    password: str,
    max_channels: int = 32,
    progress=None,
    cancel_event: Event | None = None,
    max_seconds: float = 60.0,
    rtsp_port: int = 554,
) -> list[RecorderChannel]:
    """Read-only Hikvision recorder inventory with signal-aware RTSP probing.

    0.2.22 separates *existing channels* from *active media*.  Physical inputs
    come from ISAPI Video/inputs/channels and digital/IP status comes from
    InputProxy/channels/status.  Only inputs that the recorder reports as
    active/online are RTSP-probed, avoiding long blind scans when a DVR is
    online but currently has no video signal.
    """
    started = time.monotonic()
    if not 1 <= int(rtsp_port) <= 65535:
        raise ValueError("Porta RTSP inválida")
    def route(channel: int, subtype: int) -> str:
        return hikvision_channel_url(ip, channel, subtype, port=int(rtsp_port))
    if progress:
        progress("Lendo identidade e inventário Hikvision por ISAPI somente leitura…")
    isapi = probe_hikvision_isapi_device_info(ip, username, password, timeout=3.5)
    streams = probe_hikvision_isapi_streaming_channels(ip, username, password, timeout=4.0)
    physical = probe_hikvision_isapi_video_inputs(ip, username, password, timeout=4.0)
    proxy = probe_hikvision_input_proxy_status(ip, username, password, timeout=4.0)
    configured = probe_hikvision_input_proxy_channels(ip, username, password, timeout=4.0)
    _check_cancel(cancel_event)

    if progress:
        ident = " / ".join(part for part in (isapi.manufacturer, isapi.model) if part)
        if isapi.authenticated:
            progress(
                "ISAPI autenticada" + (f" • {ident}" if ident else "")
                + f" • {physical.detail} • {proxy.detail} • {streams.detail}"
            )
        else:
            progress(f"ISAPI não confirmou a credencial ({isapi.detail}). Validando RTSP conservadoramente…")

    rows_by_channel: dict[int, RecorderChannel] = {}
    active_candidates: set[int] = set()

    # Authoritative physical-input inventory.  Keep inactive channels as
    # evidence/status rows but do not waste RTSP probes on NO VIDEO inputs.
    for row in physical.inputs:
        ch = int(row.channel_id)
        if not (1 <= ch <= 256):
            continue
        # Older firmware omits videoInputEnabled. Unknown is a candidate for
        # RTSP validation, while an explicit disabled/NO VIDEO input is skipped.
        has_signal = row.enabled is not False and row.resolution_description.strip().upper() != "NO VIDEO"
        detail_parts = ["entrada analógica"]
        if row.resolution_description:
            detail_parts.append(row.resolution_description)
        detail_parts.append("sinal não informado; testando RTSP" if has_signal and row.enabled is None
                            else "sinal informado" if has_signal else "sem sinal")
        rows_by_channel[ch] = RecorderChannel(
            ch, row.name or f"Canal {ch:02d}", route(ch, 0), False, None,
            " • ".join(detail_parts), source_name=row.name or f"Canal {ch:02d}",
            main_rtsp_url=route(ch, 0),
            sub_rtsp_url=route(ch, 1),
            channel_kind="analog",
        )
        if has_signal:
            active_candidates.add(ch)

    # Digital/IP channels may exist even when InputProxy/channels itself is
    # empty on older firmware; /status is therefore the authoritative source.
    # Configured IDs and names complement status; absence of status is unknown,
    # never automatically online. Never renumber an IP input into 1..N.
    ip_inputs = {row.channel_id: row for row in configured.channels}
    for row in proxy.channels:
        ip_inputs[row.channel_id] = row
    configured_names = {row.channel_id: row.name for row in configured.channels}
    for row in ip_inputs.values():
        ch = int(row.channel_id)
        if ch < 1 or ch > 256:
            continue
        endpoint = row.ip_address + (f":{row.port}" if row.port else "") if row.ip_address else ""
        state = "estado não informado; testando RTSP" if row.online is None else "online" if row.online else "offline"
        detail = " • ".join(part for part in (
            "canal IP", state, row.protocol, endpoint,
            (f"detecção={row.detect_result}" if row.detect_result else ""),
        ) if part)
        source_name = configured_names.get(ch) or f"Canal IP {ch:02d}"
        rows_by_channel[ch] = RecorderChannel(
            ch, source_name, route(ch, 0), False, None, detail,
            source_name=source_name,
            main_rtsp_url=route(ch, 0),
            sub_rtsp_url=route(ch, 1),
            channel_kind="ip",
        )
        if row.online is not False:
            active_candidates.add(ch)

    # Stream IDs advertised by the recorder are direct evidence of candidates.
    for ch in streams.physical_channels:
        ch = int(ch)
        if 1 <= ch <= 256:
            active_candidates.add(ch)
            rows_by_channel.setdefault(
                ch,
                RecorderChannel(
                    ch, f"Canal {ch:02d}", route(ch, 0), False,
                    source_name=f"Canal {ch:02d}", main_rtsp_url=route(ch, 0),
                    sub_rtsp_url=route(ch, 1), channel_kind="unknown",
                    detail="stream anunciado pela ISAPI; aguardando validação RTSP",
                ),
            )

    # If this firmware exposes none of the richer inventories, retain the old
    # bounded fallback instead of regressing compatibility with other models.
    authoritative_inventory = bool(physical.inputs or ip_inputs or streams.stream_ids)
    if not authoritative_inventory:
        active_candidates.update(range(1, int(max_channels) + 1))

    scan_channels = sorted(active_candidates)
    if progress:
        progress(
            f"Inventário: {len(physical.inputs)} entrada(s) física(s), {len(ip_inputs)} canal(is) IP, "
            f"{len(streams.stream_ids)} stream ID(s) anunciado(s); {len(scan_channels)} canal(is) exigem validação RTSP."
        )

    def one(ch: int) -> RecorderChannel:
        _check_cancel(cancel_event)
        main_url = route(ch, 0)
        sub_url = route(ch, 1)
        prior = rows_by_channel.get(ch)
        source_name = prior.source_name if prior else f"Canal {ch:02d}"
        channel_kind = prior.channel_kind if prior else "unknown"

        main = probe_rtsp_url_detailed(main_url, username, password)
        if main.ok:
            return RecorderChannel(
                ch, source_name, main_url, True, main.status_code, main.detail,
                source_name=source_name, main_rtsp_url=main_url, sub_rtsp_url=sub_url,
                channel_kind=channel_kind,
                **_audio_fields_for_urls((main_url, sub_url), username, password),
            )
        _check_cancel(cancel_event)
        sub = probe_rtsp_url_detailed(sub_url, username, password)
        if sub.ok:
            return RecorderChannel(
                ch, source_name, sub_url, True, sub.status_code, sub.detail,
                source_name=source_name, main_rtsp_url=main_url, sub_rtsp_url=sub_url,
                channel_kind=channel_kind,
                **_audio_fields_for_urls((sub_url, main_url), username, password),
            )
        detail = main.safe_summary() or main.detail
        if sub.detail and sub.detail != main.detail:
            detail = f"Main: {detail} • Sub: {sub.safe_summary() or sub.detail}"
        if prior and prior.detail:
            detail = f"{prior.detail} • {detail}" if detail else prior.detail
        return RecorderChannel(
            ch, source_name, main_url, False, main.status_code, detail,
            source_name=source_name, main_rtsp_url=main_url, sub_rtsp_url=sub_url,
            channel_kind=channel_kind,
        )

    if scan_channels:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="sentinel-hik-channels") as pool:
            futures = {pool.submit(one, ch): ch for ch in scan_channels}
            done = 0
            try:
                for fut in as_completed(futures):
                    _check_cancel(cancel_event)
                    if time.monotonic() - started > max_seconds:
                        raise TimeoutError("A leitura Hikvision ultrapassou o limite de tempo e foi interrompida.")
                    result = fut.result()
                    rows_by_channel[result.channel] = result
                    done += 1
                    if progress and (result.available or done % 4 == 0 or done == len(scan_channels)):
                        suffix = f" • canal {result.channel} com mídia" if result.available else ""
                        progress(f"Streams validados: {done}/{len(scan_channels)}{suffix}")
            finally:
                if cancel_event is not None and cancel_event.is_set():
                    for fut in futures:
                        fut.cancel()

    channels = sorted(rows_by_channel.values(), key=lambda c: c.channel)
    if channels and (authoritative_inventory or any(ch.available for ch in channels)):
        # Returning unavailable rows is intentional only when ISAPI supplied an
        # authoritative physical/digital inventory.  Generic fallback scans keep
        # the older compatibility-error behavior when no media validates.
        return channels

    if isapi.authenticated:
        _check_cancel(cancel_event)
        return RecorderScanResult((), identity=isapi, preserve_existing=True,
            notice="DVR autenticado e mantido no cadastro. Nenhum canal utilizável foi anunciado; "
                   "isso pode ocorrer sem câmeras ou por limitação do inventário deste firmware. "
                   "Canais anteriores foram preservados. Conecte uma câmera e repita a leitura quando desejar.")
    if isapi.status_code == 401:
        raise RtspCompatibilityError("A ISAPI rejeitou a credencial com HTTP 401 e nenhum canal pôde ser inventariado.")
    raise RtspCompatibilityError(f"Nenhum canal Hikvision pôde ser inventariado. ISAPI: {isapi.detail}.")

def diagnose_hikvision_routes(ip: str, username: str, password: str, channels,
                              *, rtsp_port: int = 554, progress=None,
                              cancel_event: Event | None = None) -> list[tuple[int, str, str, str]]:
    """Read-only Main/Sub DESCRIBE per channel, without returning credentials."""
    if not 1 <= int(rtsp_port) <= 65535:
        raise ValueError("Porta RTSP inválida")
    output = []
    for channel in sorted(set(int(ch) for ch in channels if 1 <= int(ch) <= 64)):
        _check_cancel(cancel_event)
        for subtype, label in ((0, "Main"), (1, "Sub")):
            _check_cancel(cancel_event)
            url = hikvision_channel_url(ip, channel, subtype, port=int(rtsp_port))
            report = probe_rtsp_url_detailed(url, username, password, timeout=1.5)
            detail = report.safe_summary() or report.detail
            output.append((channel, label, "RTSP/SDP OK" if report.ok else "Sem confirmação", detail))
        if progress:
            progress(f"Canal {channel}: Main/Sub testados na porta {rtsp_port}")
    return output


def hikvision_compatibility_report(ip: str, username: str, password: str, *, max_probe_channels: int = 6) -> str:
    """Generate a concise, credential-free read-only Hikvision field report."""
    info = probe_hikvision_isapi_device_info(ip, username, password, timeout=4.0)
    streams = probe_hikvision_isapi_streaming_channels(ip, username, password, timeout=4.0)
    physical = probe_hikvision_isapi_video_inputs(ip, username, password, timeout=4.0)
    proxy = probe_hikvision_input_proxy_status(ip, username, password, timeout=4.0)
    try:
        with socket.create_connection((ip, 554), timeout=1.5):
            rtsp_port = "OK"
    except OSError:
        rtsp_port = "não confirmou conexão"
    lines = [
        "Hikvision Compatibility Report — somente leitura",
        f"ISAPI DeviceInfo: {'OK' if info.authenticated else 'FALHOU'} • {info.detail}",
        f"Identidade: {(info.manufacturer + ' ' + info.model).strip() or info.model or 'não informada'}",
        f"Firmware: {info.firmware or 'não informado'}",
        f"Entradas físicas: {physical.detail}",
        f"Canais IP/digitais: {proxy.detail}",
        f"Streaming/channels: {streams.detail}",
        "IDs realmente anunciados: " + (", ".join(map(str, streams.stream_ids)) if streams.stream_ids else "nenhum"),
        f"RTSP TCP/554: {rtsp_port}",
    ]
    for row in physical.inputs[:max(1, int(max_probe_channels))]:
        signal = "com sinal" if row.enabled and row.resolution_description.strip().upper() != "NO VIDEO" else "sem sinal"
        lines.append(f"Entrada {row.channel_id:02d}: {row.name or '-'} • {signal} • {row.resolution_description or row.video_format or '-'}")
    for row in proxy.channels:
        endpoint = row.ip_address + (f":{row.port}" if row.port else "") if row.ip_address else "-"
        lines.append(
            f"Canal IP {row.channel_id:02d}: {'online' if row.online else 'offline'} • {row.protocol or '-'} • {endpoint}"
            + (f" • {row.detect_result}" if row.detect_result else "")
        )
    candidates = []
    for row in physical.inputs:
        if row.enabled and row.resolution_description.strip().upper() != "NO VIDEO":
            candidates.append(row.channel_id)
    candidates.extend(row.channel_id for row in proxy.channels if row.online)
    candidates.extend(streams.physical_channels)
    for ch in sorted(set(candidates))[:max(1, int(max_probe_channels))]:
        main = probe_rtsp_url_detailed(hikvision_channel_url(ip, ch, 0), username, password)
        sub = probe_rtsp_url_detailed(hikvision_channel_url(ip, ch, 1), username, password)
        lines.append(
            f"Canal {ch:02d}: MAIN={'OK' if main.ok else 'falhou'} ({main.safe_summary() or main.detail}); "
            f"SUB={'OK' if sub.ok else 'falhou'} ({sub.safe_summary() or sub.detail})"
        )
    if not candidates:
        lines.append("RTSP por canal: não testado porque o próprio DVR não reportou canal com sinal/online.")
    lines.append("Credenciais não são incluídas neste relatório.")
    return "\n".join(lines)

def deduplicate_equivalent_channels(channels: list[RecorderChannel]) -> list[RecorderChannel]:
    """Conservative de-duplication helper for simple IP cameras.

    This does not merge recorder channels. It is intended for future direct-IP
    camera probes where multiple vendor/OEM URL variants can point to exactly
    the same logical stream.
    """
    seen: set[tuple[str, str]] = set()
    out: list[RecorderChannel] = []
    for ch in channels:
        key = ((ch.main_rtsp_url or ch.rtsp_url).strip(), (ch.sub_rtsp_url or "").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(ch)
    return out

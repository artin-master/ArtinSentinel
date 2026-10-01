from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from urllib.parse import urlparse, urlunparse, parse_qs
from urllib.request import Request, build_opener, HTTPBasicAuthHandler, HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm
from xml.etree import ElementTree as ET

from . import __version__
from .recorder import (
    RecorderChannel, probe_rtsp_url_detailed, validate_rtsp_media,
    intelbras_channel_url_variants, hikvision_channel_url,
)
from .live import probe_rtsp_media_capabilities, authenticated_rtsp_url, ffmpeg_rtsp_timeout_args
from .akdb import audio_capability
from .xm_dvrip import dvrip_multilens_hints, probe_dvrip_media, dvrip_frame_signature, DvripError


@dataclass(slots=True)
class OnvifMediaProfile:
    token: str
    name: str
    uri: str
    width: int = 0
    height: int = 0
    encoding: str = ""


@dataclass(slots=True)
class DirectCameraScanResult:
    channels: list[RecorderChannel]
    manufacturer: str = ""
    model: str = ""
    firmware: str = ""
    serial: str = ""
    identity_source: str = ""
    recorder_detected: bool = False
    recorder_channel_hint: int = 0


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _wsse_header(username: str, password: str) -> str:
    if not username:
        return ""
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode("utf-8") + password.encode("utf-8")).digest()).decode("ascii")
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    return f"""
    <wsse:Security s:mustUnderstand="1" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
      <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>"""


def _soap(action_body: str, username: str, password: str) -> bytes:
    security = _wsse_header(username, password)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Header>{security}</s:Header>
  <s:Body>{action_body}</s:Body>
</s:Envelope>"""
    return xml.encode("utf-8")


def _post(url: str, body: bytes, username: str, password: str, timeout: float = 4.0) -> str:
    mgr = HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, url, username, password)
    opener = build_opener(HTTPDigestAuthHandler(mgr), HTTPBasicAuthHandler(mgr))
    req = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/soap+xml; charset=utf-8", "User-Agent": f"Artin-Sentinel/{__version__}"},
    )
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _find_text(root: ET.Element, localname: str) -> str:
    for elem in root.iter():
        if _local(elem.tag) == localname and elem.text:
            return elem.text.strip()
    return ""


def _device_service_candidates(ip: str, onvif_url: str) -> list[str]:
    out = []
    if onvif_url:
        out.append(onvif_url)
    out.extend([
        f"http://{ip}/onvif/device_service",
        f"http://{ip}:80/onvif/device_service",
    ])
    unique = []
    for item in out:
        if item and item not in unique:
            unique.append(item)
    return unique


def read_onvif_device_information(ip: str, username: str, password: str, onvif_url: str = "") -> dict[str, str]:
    """Read ONVIF Device Information without changing camera settings."""
    last_error = None
    for candidate in _device_service_candidates(ip, onvif_url):
        try:
            xml = _post(
                candidate,
                _soap('<tds:GetDeviceInformation xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>', username, password),
                username, password,
            )
            root = ET.fromstring(xml)
            return {
                "manufacturer": _find_text(root, "Manufacturer"),
                "model": _find_text(root, "Model"),
                "firmware": _find_text(root, "FirmwareVersion"),
                "serial": _find_text(root, "SerialNumber"),
                "source": "ONVIF GetDeviceInformation",
            }
        except Exception as exc:
            last_error = exc
    if last_error:
        raise RuntimeError(f"ONVIF Device Information não respondeu: {type(last_error).__name__}")
    return {}


def read_onvif_media_profiles(ip: str, username: str, password: str, onvif_url: str = "") -> list[OnvifMediaProfile]:
    """Read ONVIF media profiles using only read-only SOAP operations.

    The implementation intentionally has no dependency on a vendor SDK. It tries
    WS-Security UsernameToken plus HTTP Digest/Basic, which covers many cameras.
    Unsupported devices simply fall back to provider RTSP patterns.
    """
    device_url = ""
    capabilities_xml = ""
    last_error = None
    for candidate in _device_service_candidates(ip, onvif_url):
        try:
            capabilities_xml = _post(
                candidate,
                _soap(
                    '<tds:GetCapabilities xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><tds:Category>Media</tds:Category></tds:GetCapabilities>',
                    username,
                    password,
                ),
                username,
                password,
            )
            device_url = candidate
            break
        except Exception as exc:
            last_error = exc
    if not capabilities_xml:
        if last_error:
            raise RuntimeError(f"ONVIF Device não respondeu: {type(last_error).__name__}")
        return []

    root = ET.fromstring(capabilities_xml)
    media_url = ""
    for elem in root.iter():
        if _local(elem.tag) == "Media":
            for child in elem.iter():
                if _local(child.tag) == "XAddr" and child.text:
                    media_url = child.text.strip()
                    break
        if media_url:
            break
    if not media_url:
        parsed = urlparse(device_url)
        media_url = urlunparse((parsed.scheme, parsed.netloc, "/onvif/media_service", "", "", ""))

    profiles_xml = _post(
        media_url,
        _soap('<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>', username, password),
        username,
        password,
    )
    profiles_root = ET.fromstring(profiles_xml)
    records: list[tuple[str, str, int, int, str]] = []
    for elem in profiles_root.iter():
        if _local(elem.tag) != "Profiles":
            continue
        token = elem.attrib.get("token", "")
        name = ""
        width = height = 0
        encoding = ""
        for child in elem.iter():
            lname = _local(child.tag)
            if lname == "Name" and not name and child.text:
                name = child.text.strip()
            elif lname == "Width" and child.text:
                try: width = int(child.text)
                except ValueError: pass
            elif lname == "Height" and child.text:
                try: height = int(child.text)
                except ValueError: pass
            elif lname == "Encoding" and child.text:
                encoding = child.text.strip()
        if token:
            records.append((token, name or token, width, height, encoding))

    out: list[OnvifMediaProfile] = []
    for token, name, width, height, encoding in records:
        get_uri = f"""
        <trt:GetStreamUri xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
          <trt:StreamSetup>
            <tt:Stream xmlns:tt="http://www.onvif.org/ver10/schema">RTP-Unicast</tt:Stream>
            <tt:Transport xmlns:tt="http://www.onvif.org/ver10/schema"><tt:Protocol>RTSP</tt:Protocol></tt:Transport>
          </trt:StreamSetup>
          <trt:ProfileToken>{token}</trt:ProfileToken>
        </trt:GetStreamUri>"""
        try:
            uri_xml = _post(media_url, _soap(get_uri, username, password), username, password)
            uri_root = ET.fromstring(uri_xml)
            uri = _find_text(uri_root, "Uri")
        except Exception:
            uri = ""
        if uri:
            out.append(OnvifMediaProfile(token, name, uri, width, height, encoding))
    return out


def direct_camera_provider_hint(provider: str, manufacturer: str = "", model: str = "", name: str = "") -> str:
    """Return the safest direct-camera provider hint from stored/manual identity.

    Manual identity must never become AKDB evidence, but it is useful as an
    operator hint to choose which *read-only* RTSP candidates to validate.
    The returned provider only changes the order/set of probes; every URL still
    needs ffprobe/libavformat confirmation before it is persisted.
    """
    current = (provider or "generic").lower()
    text = f"{manufacturer} {model} {name}".lower()
    if ("aitek" in text or "aiktek" in text or "sigma-seg6050bp" in text or "h2-52pgx" in text):
        return "aitek"
    if "it-blue" in text or "it blue" in text or any(token in text for token in ("x3-we2q", "xm535d1", "000a06cd", "gk7202v300")):
        return "it-blue"
    if "mibo" in text or ("intelbras" in text and any(token in text for token in ("imx", "imx c", "im c"))):
        return "intelbras-mibo"
    if "intelbras" in text and any(token in text for token in ("vipc", "vip ", "vip-")):
        return "intelbras"
    if "hikvision" in text:
        return "hikvision"
    if "jfl" in text:
        return "jfl"
    return current


def _candidate_pairs(ip: str, provider: str, rtsp_url: str = "") -> list[tuple[str, str, str]]:
    provider = (provider or "").lower()
    pairs: list[tuple[str, str, str]] = []
    if provider in {"hikvision", "jfl"}:
        pairs.append(("Hikvision", hikvision_channel_url(ip, 1, 0), hikvision_channel_url(ip, 1, 1)))
    if provider in {"intelbras", "intelbras-mibo"}:
        # Intelbras Mibo generations share more than one RTSP dialect.  The
        # realmonitor path is currently documented for iMX-C, while older Mibo
        # models have also exposed /live or /live/mpeg4.  Every candidate is
        # media-validated before it can be persisted.
        pairs.extend([
            ("Intelbras/Dahua", intelbras_channel_url_variants(ip, 1, 0)[0], intelbras_channel_url_variants(ip, 1, 1)[0]),
            ("Intelbras ONVIF query", f"rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif", f"rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=1&unicast=true&proto=Onvif"),
            ("Mibo legacy live", f"rtsp://{ip}:554/live", ""),
            ("Mibo legacy mpeg4", f"rtsp://{ip}:554/live/mpeg4", ""),
        ])
    if provider == "aitek":
        # Field-validated Aitek SIGMA-SEG6050BP / H2-52PGX profile. The camera
        # itself documents /live/0/MAIN and /live/0/SUB on RTSP/554. Keep this
        # pair first so local access is deterministic before OEM fallbacks.
        # Every candidate is still ffprobe-validated before persistence.
        pairs.extend([
            ("Aitek SIGMA H2-52PGX", f"rtsp://{ip}:554/live/0/MAIN", f"rtsp://{ip}:554/live/0/SUB"),
            ("Aitek RTSP root", f"rtsp://{ip}:554/", ""),
            ("Aitek ch01", f"rtsp://{ip}:554/ch01/0", f"rtsp://{ip}:554/ch01/1"),
            ("Aitek ch0 stream", f"rtsp://{ip}:554/ch0/stream0", f"rtsp://{ip}:554/ch0/stream1"),
            ("Aitek snl", f"rtsp://{ip}:554/snl/live/1/1", f"rtsp://{ip}:554/snl/live/1/2"),
            ("Aitek/XM underscore", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=1_stream=0.sdp", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=1_stream=1.sdp"),
            ("Aitek/XM underscore real_stream", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=1_stream=0.sdp?real_stream", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=1_stream=1.sdp?real_stream"),
            ("Aitek/XM ampersand", f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel=1&stream=0.sdp", f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel=1&stream=1.sdp"),
            ("Aitek/XM ampersand real_stream", f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel=1&stream=0.sdp?real_stream", f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel=1&stream=1.sdp?real_stream"),
        ])
    if provider == "it-blue":
        # IT-Blue Speed Dome X3-WE2Q / XM535D1 candidate set. Field evidence
        # identifies the platform; each URL is still ffprobe-validated before
        # persistence because OEM firmware can vary by build. Channel=0 is
        # important on this iCSee/XM family. /onvif1 is a common local stream
        # alias and remains only a candidate until media validation succeeds.
        pairs.extend([
            ("IT-Blue X3-WE2Q XM ch0", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=0_stream=0.sdp?real_stream", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=0_stream=1.sdp?real_stream"),
            ("IT-Blue X3-WE2Q onvif", f"rtsp://{ip}:554/onvif1", f"rtsp://{ip}:554/onvif2"),
            ("IT-Blue/XM template ch1", f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel=1&stream=0.sdp?real_stream", f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel=1&stream=1.sdp?real_stream"),
            ("IT-Blue/XM underscore ch1", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=1_stream=0.sdp?real_stream", f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel=1_stream=1.sdp?real_stream"),
            ("IT-Blue 11/12", f"rtsp://{ip}:554/11", f"rtsp://{ip}:554/12"),
        ])
    # Conservative generic patterns used only as fallbacks and always media-validated.
    pairs.extend([
        ("Generic 101/102", f"rtsp://{ip}:554/Streaming/Channels/101", f"rtsp://{ip}:554/Streaming/Channels/102"),
        ("Generic Dahua", f"rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=0", f"rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=1"),
        ("Generic live", f"rtsp://{ip}:554/live/ch00_0", f"rtsp://{ip}:554/live/ch00_1"),
        ("Generic av_stream", f"rtsp://{ip}:554/h264/ch1/main/av_stream", f"rtsp://{ip}:554/h264/ch1/sub/av_stream"),
        ("Generic 11/12", f"rtsp://{ip}:554/11", f"rtsp://{ip}:554/12"),
    ])
    if rtsp_url and rtsp_url.rstrip("/") not in {f"rtsp://{ip}:554", f"rtsp://{ip}:554/"}:
        pairs.insert(0, ("Descoberto", rtsp_url, ""))
    seen = set()
    result = []
    for label, main, sub in pairs:
        key = (main, sub)
        if key not in seen:
            seen.add(key)
            result.append((label, main, sub))
    return result


def _direct_audio_fields(provider: str, url: str, username: str, password: str) -> dict:
    known = audio_capability(provider=provider)
    probe = probe_rtsp_media_capabilities(url, username, password) if url else None
    mode = str(known.get("mode") or "unknown")
    if probe and probe.has_audio and mode in {"unknown", "none"}:
        mode = "listen"
    if probe and probe.ok and not probe.has_audio and mode == "unknown":
        mode = "none"
    codec = probe.audio_codec if probe else ""
    rate = probe.audio_sample_rate if probe else 0
    channels = probe.audio_channels if probe else 0
    detail_parts = []
    if codec:
        detail_parts.append(codec + (f" {rate} Hz" if rate else ""))
    if mode == "bidirectional":
        protocol = str(known.get("talkback_protocol") or "")
        detail_parts.append("talkback " + ("a validar" if protocol == "unvalidated" else protocol or "detectado"))
    return {
        "audio_mode": mode,
        "audio_codec": codec,
        "audio_sample_rate": rate,
        "audio_channels": channels,
        "audio_detail": " • ".join(detail_parts),
    }


def _video_frame_fingerprint(url: str, username: str, password: str, timeout: float = 8.0) -> str:
    """Hash one tiny decoded frame so OEM aliases do not become fake cameras."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not url:
        return ""
    auth_url = authenticated_rtsp_url(url, username, password)
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", *list(ffmpeg_rtsp_timeout_args()),
        "-i", auth_url, "-frames:v", "1",
        "-vf", "scale=160:90,format=gray", "-f", "hash", "-hash", "sha256", "-",
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if cp.returncode != 0:
        return ""
    match = re.search(r"SHA256=([0-9a-fA-F]{64})", cp.stdout or "")
    return match.group(1).lower() if match else ""


def _video_frame_signature(url: str, username: str, password: str, timeout: float = 8.0) -> int | None:
    """Return a small perceptual signature robust to timestamps/encoding aliases.

    Exact frame hashes are unsuitable for OEM aliases because the same lens is
    decoded a fraction of a second later and overlays may have changed.  This
    signature crops the lower quarter (where timestamps commonly live), scales
    to 16x9 grayscale and compares luminance topology instead of encoded bytes.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not url:
        return None
    auth_url = authenticated_rtsp_url(url, username, password)
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", *list(ffmpeg_rtsp_timeout_args()),
        "-i", auth_url, "-frames:v", "1",
        # Use the central scene area: field cameras place timestamps/status
        # overlays near the top/right edges, which made the same lens look
        # different between probes in 0.2.17.
        "-vf", "crop=trunc(iw*0.72):trunc(ih*0.62):trunc(iw*0.14):trunc(ih*0.19),scale=16:9,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    data = cp.stdout or b""
    if cp.returncode != 0 or len(data) < 144:
        return None
    pixels = data[:144]
    avg = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | int(value >= avg)
    return bits


def _signature_distance(a, b) -> int:
    if a is None or b is None:
        return 10**9
    if isinstance(a, int) and isinstance(b, int):
        return (a ^ b).bit_count()
    return 0 if a == b else 10**9


def _same_visual_stream(signature, existing: list, *, threshold: int = 14) -> bool:
    return signature is not None and any(_signature_distance(signature, item) <= threshold for item in existing)


def _route_frame_signature(url: str, username: str, password: str):
    parsed = urlparse(url)
    if parsed.scheme == "dvrip" and parsed.hostname:
        query = parse_qs(parsed.query)
        try:
            channel = int((query.get("channel") or ["0"])[0])
            subtype = int((query.get("subtype") or ["0"])[0])
        except (TypeError, ValueError):
            return None
        return dvrip_frame_signature(parsed.hostname, username, password,
                                     channel=channel, subtype=subtype)
    sig = _video_frame_signature(url, username, password, timeout=4.0)
    return sig if sig is not None else _video_frame_fingerprint(url, username, password, timeout=4.0) or None


def _paired_visual_alias(candidate_url: str, accepted_urls: list[str], username: str, password: str, *, threshold: int = 24) -> bool:
    """Re-capture candidate and accepted streams nearly simultaneously.

    A PTZ view can move between sequential probes, which made the same encoder
    look like a new physical lens. Two paired rounds are required before a
    candidate is promoted; if either round matches an accepted source, it is
    conservatively treated as an alias.
    """
    if not candidate_url or not accepted_urls:
        return False
    accepted_urls = [u for u in accepted_urls if u]
    if not accepted_urls:
        return False
    rounds = []
    for _round in range(3):
        urls = [candidate_url, *accepted_urls]
        def capture(u):
            return _route_frame_signature(u, username, password)
        with ThreadPoolExecutor(max_workers=min(4, len(urls)), thread_name_prefix="sentinel-lens-fp") as pool:
            sigs = list(pool.map(capture, urls))
        candidate_sig = sigs[0]
        if candidate_sig is None:
            return True  # insufficient evidence: do not promote a new lens
        if any(sig is None for sig in sigs[1:]):
            return True
        rounds.append(sigs)
        for existing_sig in sigs[1:]:
            if existing_sig is not None and _signature_distance(candidate_sig, existing_sig) <= threshold:
                return True
        if _round < 2:
            time.sleep(0.15)
    # If either view changed substantially while the paired samples were
    # captured, even a second route to the moving PTZ can look like a distinct
    # camera. Defer classification until a stable observation or native channel.
    for column in range(len(rounds[0])):
        if any(_signature_distance(rounds[0][column], sample[column]) > threshold for sample in rounds[1:]):
            return True
    return False


def _x3_logical_channel(logical_key: str) -> int:
    """Keep a physical lens in the same slot even when another lens is offline."""
    family, _, value = logical_key.partition(":")
    try:
        n = int(value)
    except ValueError:
        return 0
    if family in {"xm", "short"}:
        return n + 1 if n in (0, 1, 2) else 0
    if family == "onvif":
        return {1: 1, 3: 2, 5: 3}.get(n, 0)
    return 0


def _scan_itblue_x3_multilens_rtsp(ip: str, username: str, password: str, progress=None, cancel_event: Event | None = None) -> list[RecorderChannel]:
    """Find up to three visually distinct lenses without promoting aliases.

    0.2.19 keeps the exhaustive fallbacks from 0.2.17, but reduces field scan
    time by validating one stream first and probing its companion Main/Sub only
    after the view is accepted. Alternate credential syntax for the same XM
    channel is skipped once that channel already returned usable video.
    """
    native_hints = {}
    try:
        native_hints = dvrip_multilens_hints(ip, username, password, timeout=2.5)
    except (DvripError, OSError):
        native_hints = {}
    hinted = int(native_hints.get("channel_count_hint") or 0)
    max_xm_channel = min(max(hinted, 4), 8)
    if progress:
        objects = ", ".join(native_hints.get("config_objects") or ()) or "nenhum"
        progress(f"IT-Blue X3: DVRIP somente leitura • canais sugeridos={hinted or 'não informado'} • objetos={objects}.")

    candidates: list[tuple[str, str, str, str]] = []
    for channel in range(0, max_xm_channel):
        candidates.extend([
            (
                f"xm:{channel}", f"XM underscore ch{channel}",
                f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel={channel}_stream=0.sdp?real_stream",
                f"rtsp://{ip}:554/user={{username}}_password={{password}}_channel={channel}_stream=1.sdp?real_stream",
            ),
            (
                f"xm:{channel}", f"XM ampersand ch{channel}",
                f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel={channel}&stream=0.sdp?real_stream",
                f"rtsp://{ip}:554/user={{username}}&password={{password}}&channel={channel}&stream=1.sdp?real_stream",
            ),
        ])
    # X3-WE2Q field/community reports show some firmware exposing a short
    # numeric RTSP alias (for example /1) instead of per-lens XM query URLs.
    # Probe /0.. /3 conservatively and let visual deduplication decide whether
    # any alias is a genuinely distinct physical view.
    for numeric in range(0, 4):
        candidates.append((
            f"short:{numeric}", f"RTSP curto /{numeric}",
            f"rtsp://{ip}:554/{numeric}", "",
        ))
    for profile in (1, 3, 5):
        candidates.append((
            f"onvif:{profile}", f"ONVIF alias {profile}/{profile + 1}",
            f"rtsp://{ip}:554/onvif{profile}", f"rtsp://{ip}:554/onvif{profile + 1}",
        ))

    channels: list[RecorderChannel] = []
    signatures: list = []
    accepted_urls: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()
    logical_with_video: set[str] = set()
    total = len(candidates)
    for idx, (logical_key, label, main_url, sub_url) in enumerate(candidates, start=1):
        if len(channels) >= 3:
            break
        number = _x3_logical_channel(logical_key)
        if not number or any(ch.channel == number for ch in channels):
            continue
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Teste cancelado.")
        key = (main_url, sub_url)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        if logical_key in logical_with_video:
            # A working spelling for this physical XM channel was already
            # proven. The alternate username/password separator cannot expose
            # another lens, so avoid another expensive FFprobe cycle.
            continue
        if progress:
            progress(f"IT-Blue X3: {idx}/{total} • procurando visão distinta • {label}…")

        main_ok, main_detail = validate_rtsp_media(main_url, username, password, timeout=3.2)
        sub_ok = False
        sub_detail = ""
        chosen = main_url if main_ok else ""
        chosen_detail = main_detail if main_ok else ""
        if not main_ok and sub_url:
            sub_ok, sub_detail = validate_rtsp_media(sub_url, username, password, timeout=3.2)
            if sub_ok:
                chosen, chosen_detail = sub_url, sub_detail
        if not chosen:
            continue
        logical_with_video.add(logical_key)

        signature = _video_frame_signature(chosen, username, password, timeout=5.0)
        if signature is None:
            signature = _video_frame_fingerprint(chosen, username, password) or None
        if signature is None:
            if channels:
                if progress:
                    progress(f"IT-Blue X3: {label} tem vídeo, mas sem assinatura visual; não promovido como nova lente.")
                continue
        elif _same_visual_stream(signature, signatures, threshold=22):
            if progress:
                progress(f"IT-Blue X3: {label} repete a mesma lente; alias descartado.")
            continue
        elif accepted_urls and _paired_visual_alias(chosen, accepted_urls, username, password, threshold=26):
            if progress:
                progress(f"IT-Blue X3: {label} coincide com uma lente já aceita em captura simultânea; alias descartado.")
            continue
        if signature is not None:
            signatures.append(signature)
        accepted_urls.append(chosen)

        # Only after a distinct lens is accepted do we spend another probe to
        # discover its companion profile. This materially shortens field scans.
        if main_ok and not sub_ok and sub_url:
            sub_ok, sub_detail = validate_rtsp_media(sub_url, username, password, timeout=3.2)
        elif sub_ok and not main_ok and main_url:
            main_ok, main_detail = validate_rtsp_media(main_url, username, password, timeout=3.2)

        source_name = "Lente PTZ" if number == 1 else f"Lente fixa {number - 1}"
        channel_name = f"Câmera {number:02d}"
        channels.append(RecorderChannel(
            number, channel_name, chosen, True, 200,
            f"Rota direta • IT-Blue X3 • {source_name} • {label} • {chosen_detail}",
            source_name=source_name,
            main_rtsp_url=main_url if main_ok else "",
            sub_rtsp_url=sub_url if sub_ok else "",
            route_kind="direct", channel_kind="ip",
            **_direct_audio_fields("it-blue", chosen, username, password),
        ))
    # On X3-WE2Q/XM535D1 field hardware the RTSP server may expose only the
    # PTZ lens even when channel=1/2 is requested. Check native fixed channels
    # even if RTSP appeared to find three: a moving PTZ can fool frame-based
    # deduplication, while an OPMonitor channel has a stable hardware slot.
    native_candidates = (0, 1, 2) if not any(ch.channel == 1 for ch in channels) else (1, 2)
    for native_channel in native_candidates:
        if native_channel == 0 and any(ch.channel == 1 for ch in channels):
            continue
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Teste cancelado.")
        if progress:
            progress(f"IT-Blue X3: verificando lente nativa DVRIP canal {native_channel}…")
        main_probe = probe_dvrip_media(
            ip, username, password, channel=native_channel, subtype=0, timeout=4.0
        )
        sub_probe = None
        if main_probe.ok:
            sub_probe = probe_dvrip_media(
                ip, username, password, channel=native_channel, subtype=1, timeout=2.5
            )
        else:
            # Some firmware exposes only Extra1 until its Main encoder wakes.
            sub_probe = probe_dvrip_media(
                ip, username, password, channel=native_channel, subtype=1, timeout=3.0
            )
        if not main_probe.ok and not (sub_probe and sub_probe.ok):
            if progress:
                progress(f"IT-Blue X3: DVRIP canal {native_channel} sem vídeo no Main/Sub • "
                         f"Main: {main_probe.detail} • Sub: {sub_probe.detail if sub_probe else 'não testado'}")
            continue
        main_url = f"dvrip://{ip}:34567?channel={native_channel}&subtype=0" if main_probe.ok else ""
        sub_url = f"dvrip://{ip}:34567?channel={native_channel}&subtype=1" if sub_probe and sub_probe.ok else ""
        chosen = main_url or sub_url
        number = native_channel + 1
        other_urls = [ch.rtsp_url for ch in channels if ch.channel != number and ch.rtsp_url]
        # A response on a distinct DVRIP channel number does not prove a
        # distinct image. Decode and compare alongside the PTZ and accepted
        # fixed lenses before replacing any route or advertising a new one.
        native_sig = _route_frame_signature(chosen, username, password)
        if native_sig is None or (other_urls and _paired_visual_alias(chosen, other_urls, username, password, threshold=26)):
            if progress:
                progress(f"IT-Blue X3: DVRIP canal {native_channel} sem imagem distinta comprovada; rota não promovida.")
            # The RTSP route in this same slot has already passed the visual
            # test; retain it if native comparison was inconclusive.
            continue
        if native_channel == 0:
            source_name = "Lente PTZ"
        else:
            source_name = f"Lente fixa {1 if native_channel == 1 else 2}"
        # A native fixed channel supersedes a provisional RTSP alias in the
        # same slot; do not silently create a fourth logical lens.
        channels = [ch for ch in channels if ch.channel != number]
        channel_name = f"Câmera {number:02d}"
        codec = main_probe.codec if main_probe.ok else (sub_probe.codec if sub_probe else "")
        detail = main_probe.detail if main_probe.ok else (sub_probe.detail if sub_probe else "DVRIP")
        channels.append(RecorderChannel(
            number, channel_name, chosen, True, 200,
            f"Rota direta • IT-Blue X3 • {source_name} • DVRIP nativo • {detail}",
            source_name=source_name,
            main_rtsp_url=main_url, sub_rtsp_url=sub_url,
            route_kind="direct", channel_kind="ip",
            audio_mode="none", audio_codec="", audio_sample_rate=0, audio_channels=0,
            audio_detail=f"Vídeo nativo DVRIP {codec.upper() if codec else 'validado'}; áudio desta lente não anunciado",
        ))

    channels.sort(key=lambda ch: ch.channel)

    if progress:
        progress(f"IT-Blue X3: {len(channels)}/3 visão(ões) local(is) com comparação visual validada (RTSP/DVRIP).")
        if len(channels) < 3:
            missing = ", ".join(name for number, name in ((1, "PTZ"), (2, "fixa 1"), (3, "fixa 2"))
                                if not any(channel.channel == number for channel in channels))
            progress(f"IT-Blue X3: lente(s) sem vídeo distinto comprovado: {missing}. Consulte Logs e diagnóstico → Leitura RTSP.")
    return channels

def scan_direct_camera_streams(
    ip: str,
    username: str,
    password: str,
    *,
    provider: str = "generic",
    manufacturer_hint: str = "",
    model_hint: str = "",
    name_hint: str = "",
    onvif_url: str = "",
    rtsp_url: str = "",
    progress=None,
    cancel_event: Event | None = None,
) -> DirectCameraScanResult:
    """Resolve and *media-validate* one direct IP camera channel.

    A direct camera is not inserted into Live View merely because an RTSP
    endpoint answers DESCRIBE.  At least one URL must expose a decodable video
    stream through ffprobe/libavformat when ffprobe is available.
    """
    provider = direct_camera_provider_hint(provider, manufacturer_hint, model_hint, name_hint)
    identity: dict[str, str] = {}
    if progress:
        progress(f"Câmera IP: provider de teste {provider}; lendo identidade ONVIF e Media Profiles…")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Teste cancelado.")

    try:
        identity = read_onvif_device_information(ip, username, password, onvif_url)
        if progress and (identity.get("manufacturer") or identity.get("model")):
            label = " ".join(x for x in (identity.get("manufacturer", ""), identity.get("model", "")) if x)
            progress(f"ONVIF identificou: {label}.")
    except Exception as exc:
        if progress:
            progress(f"ONVIF Device Information não confirmou identidade ({type(exc).__name__}).")

    # A generic ONVIF scope can identify a Hikvision DVR as a single camera.
    # Confirm a recorder from its exact model or multiple physical ISAPI inputs
    # before probing one camera profile and losing the remaining channels.
    if provider == "hikvision":
        from .akdb import best_profile, routing_kind_for_profile
        from .native_protocols import probe_hikvision_isapi_video_inputs, probe_hikvision_isapi_device_info
        info = probe_hikvision_isapi_device_info(ip, username, password, timeout=3.5)
        model = info.model or identity.get("model", "") or model_hint
        match = best_profile(text=model, manufacturer="Hikvision") if model else None
        exact_recorder = bool(match and match[0] >= 90 and
                              routing_kind_for_profile(match[1].key) in {"dvr", "nvr", "xvr"})
        physical = probe_hikvision_isapi_video_inputs(ip, username, password, timeout=4.0)
        count = len(physical.inputs) if physical.ok else 0
        if exact_recorder or count > 1:
            if progress:
                progress(f"Hikvision: gravador confirmado • {model or 'modelo não informado'} • "
                         f"{count or 'múltiplas'} entradas; iniciando leitura de canais.")
            return DirectCameraScanResult(
                channels=[], manufacturer=info.manufacturer or identity.get("manufacturer", "Hikvision"),
                model=model, firmware=info.firmware or identity.get("firmware", ""),
                identity_source="ISAPI/ONVIF", recorder_detected=True, recorder_channel_hint=count,
            )

    if provider == "it-blue":
        x3_channels = _scan_itblue_x3_multilens_rtsp(ip, username, password, progress, cancel_event)
        if x3_channels:
            return DirectCameraScanResult(
                channels=x3_channels,
                manufacturer=identity.get("manufacturer", ""),
                model=identity.get("model", ""),
                firmware=identity.get("firmware", ""),
                serial=identity.get("serial", ""),
                identity_source=identity.get("source", ""),
            )

    profiles: list[OnvifMediaProfile] = []
    try:
        profiles = read_onvif_media_profiles(ip, username, password, onvif_url)
    except Exception as exc:
        if progress:
            progress(f"ONVIF não confirmou Media Profiles ({type(exc).__name__}). Tentando RTSP pela AKDB/provider…")

    valid_profiles: list[tuple[OnvifMediaProfile, str]] = []
    for profile in profiles:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Teste cancelado.")
        ok, media_detail = validate_rtsp_media(profile.uri, username, password)
        if ok:
            valid_profiles.append((profile, media_detail))
    if valid_profiles:
        valid_profiles.sort(key=lambda item: (item[0].width * item[0].height, item[0].width, item[0].height), reverse=True)
        main, main_probe = valid_profiles[0]
        sub = ""
        for profile, _probe in reversed(valid_profiles):
            if profile.uri != main.uri:
                sub = profile.uri
                break
        detail = f"ONVIF GetStreamUri • {main_probe}"
        if progress:
            progress(f"ONVIF confirmou {len(valid_profiles)} perfil(is) com vídeo decodificável.")
        return DirectCameraScanResult(
            channels=[RecorderChannel(
                1, "Câmera 01", main.uri, True, 200, detail,
                source_name="Câmera 01", main_rtsp_url=main.uri, sub_rtsp_url=sub,
                route_kind="direct", channel_kind="ip",
                **_direct_audio_fields(provider, main.uri, username, password),
            )],
            manufacturer=identity.get("manufacturer", ""),
            model=identity.get("model", ""),
            firmware=identity.get("firmware", ""),
            serial=identity.get("serial", ""),
            identity_source=identity.get("source", ""),
        )

    if progress:
        progress("ONVIF sem vídeo utilizável. Testando padrões RTSP conhecidos com ffprobe…")
    failures: list[str] = []
    for label, main_url, sub_url in _candidate_pairs(ip, provider, rtsp_url):
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Teste cancelado.")
        if progress:
            progress(f"RTSP: testando {label}…")
        main_ok, main_detail = validate_rtsp_media(main_url, username, password)
        sub_ok = False
        sub_detail = ""
        if sub_url:
            sub_ok, sub_detail = validate_rtsp_media(sub_url, username, password)
        if main_ok or sub_ok:
            chosen = main_url if main_ok else sub_url
            evidence = main_detail if main_ok else sub_detail
            if progress:
                audio = _direct_audio_fields(provider, chosen, username, password)
                audio_text = audio.get("audio_codec") or audio.get("audio_mode") or "não identificado"
                progress(f"RTSP confirmado pela assinatura {label}: {evidence}. Áudio: {audio_text}.")
            return DirectCameraScanResult(
                channels=[RecorderChannel(
                    1, "Câmera 01", chosen, True, 200,
                    f"Rota direta • {label} • {evidence}",
                    source_name="Câmera 01",
                    main_rtsp_url=main_url if main_ok else "",
                    sub_rtsp_url=sub_url if sub_ok else "",
                    route_kind="direct", channel_kind="ip",
                    **_direct_audio_fields(provider, chosen, username, password),
                )],
                manufacturer=identity.get("manufacturer", ""),
                model=identity.get("model", ""),
                firmware=identity.get("firmware", ""),
                serial=identity.get("serial", ""),
                identity_source=identity.get("source", ""),
            )
        detail = main_detail or sub_detail or "sem confirmação"
        failures.append(f"{label}: {detail}")

    tail = "; ".join(failures[-4:])
    extra = f" Últimas tentativas: {tail}." if tail else ""
    raise RuntimeError(
        "A câmera responde na rede, mas nenhum stream de vídeo foi validado. "
        "O Sentinel não vai iniciar reconexão contínua sem uma URL confirmada. "
        "Verifique credencial/ONVIF/RTSP no equipamento." + extra
    )

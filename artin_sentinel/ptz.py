from __future__ import annotations

"""Local PTZ control helpers.

The first implementation deliberately uses standards-based ONVIF PTZ only.
Vendor/cloud control is not attempted here. Commands are explicit operator
requests; no background movement or automatic tracking control is performed.
"""

from dataclasses import dataclass
from html import escape
from math import isfinite
from time import sleep
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

from .ip_camera import _device_service_candidates, _find_text, _local, _post, _soap


@dataclass(frozen=True, slots=True)
class OnvifPtzContext:
    device_url: str
    media_url: str
    ptz_url: str
    profile_token: str


def _xaddr_from_capabilities(root: ET.Element, service_name: str) -> str:
    for elem in root.iter():
        if _local(elem.tag) != service_name:
            continue
        for child in elem.iter():
            if _local(child.tag) == "XAddr" and child.text:
                return child.text.strip()
    return ""


def _fallback_service(device_url: str, path: str) -> str:
    parsed = urlparse(device_url)
    return urlunparse((parsed.scheme or "http", parsed.netloc, path, "", "", ""))


def discover_onvif_ptz_context(
    ip: str,
    username: str,
    password: str,
    onvif_url: str = "",
    *,
    timeout: float = 4.0,
) -> OnvifPtzContext:
    """Resolve PTZ service and a usable media profile without changing settings."""
    last_error: Exception | None = None
    for device_url in _device_service_candidates(ip, onvif_url):
        try:
            cap_xml = _post(
                device_url,
                _soap(
                    '<tds:GetCapabilities xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><tds:Category>All</tds:Category></tds:GetCapabilities>',
                    username,
                    password,
                ),
                username,
                password,
                timeout=timeout,
            )
            root = ET.fromstring(cap_xml)
            media_url = _xaddr_from_capabilities(root, "Media") or _fallback_service(device_url, "/onvif/media_service")
            ptz_url = _xaddr_from_capabilities(root, "PTZ") or _fallback_service(device_url, "/onvif/ptz_service")
            profiles_xml = _post(
                media_url,
                _soap('<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>', username, password),
                username,
                password,
                timeout=timeout,
            )
            profiles_root = ET.fromstring(profiles_xml)
            token = ""
            for elem in profiles_root.iter():
                if _local(elem.tag) == "Profiles" and elem.attrib.get("token"):
                    # A media profile alone is not evidence of PTZ capability.
                    has_ptz = any(_local(child.tag) == "PTZConfiguration" for child in elem.iter())
                    if has_ptz:
                        token = elem.attrib["token"]
                        break
            if not token:
                raise RuntimeError("ONVIF não retornou Media Profile com PTZConfiguration")
            return OnvifPtzContext(device_url, media_url, ptz_url, token)
        except Exception as exc:  # try the next device-service candidate
            last_error = exc
    if last_error:
        raise RuntimeError(f"ONVIF PTZ indisponível: {type(last_error).__name__}")
    raise RuntimeError("ONVIF PTZ indisponível")


def _velocity(direction: str, speed: float) -> tuple[float, float, float]:
    if not isfinite(float(speed)):
        raise ValueError("Velocidade PTZ inválida")
    speed = max(0.05, min(float(speed), 1.0))
    direction = (direction or "").lower()
    values = {
        "left": (-speed, 0.0, 0.0),
        "right": (speed, 0.0, 0.0),
        "up": (0.0, speed, 0.0),
        "down": (0.0, -speed, 0.0),
        "up-left": (-speed, speed, 0.0),
        "up-right": (speed, speed, 0.0),
        "down-left": (-speed, -speed, 0.0),
        "down-right": (speed, -speed, 0.0),
        "zoom-in": (0.0, 0.0, speed),
        "zoom-out": (0.0, 0.0, -speed),
    }
    if direction not in values:
        raise ValueError(f"Direção PTZ inválida: {direction}")
    return values[direction]


def continuous_move(
    context: OnvifPtzContext,
    username: str,
    password: str,
    direction: str,
    speed: float = 0.45,
    *,
    timeout_seconds: float = 0.35,
) -> None:
    """Send one bounded ONVIF ContinuousMove command.

    A Timeout is included so a dropped Stop request cannot leave a camera moving.
    """
    direction = (direction or "").lower()
    x, y, z = _velocity(direction, speed)
    token = escape(context.profile_token, quote=True)
    timeout_seconds = max(0.10, min(float(timeout_seconds), 1.5))
    velocity_parts = []
    if direction.startswith("zoom"):
        velocity_parts.append(
            f'<tt:Zoom x="{z:.3f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/VelocityGenericSpace"/>'
        )
    else:
        velocity_parts.append(
            f'<tt:PanTilt x="{x:.3f}" y="{y:.3f}" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"/>'
        )
    body = f"""
<tptz:ContinuousMove xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <tptz:ProfileToken>{token}</tptz:ProfileToken>
  <tptz:Velocity>{''.join(velocity_parts)}</tptz:Velocity>
  <tptz:Timeout>PT{timeout_seconds:.2f}S</tptz:Timeout>
</tptz:ContinuousMove>"""
    _post(context.ptz_url, _soap(body, username, password), username, password, timeout=4.0)


def stop(context: OnvifPtzContext, username: str, password: str) -> None:
    token = escape(context.profile_token, quote=True)
    body = f"""
<tptz:Stop xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
  <tptz:ProfileToken>{token}</tptz:ProfileToken>
  <tptz:PanTilt>true</tptz:PanTilt>
  <tptz:Zoom>true</tptz:Zoom>
</tptz:Stop>"""
    _post(context.ptz_url, _soap(body, username, password), username, password, timeout=4.0)


def start_move(
    ip: str,
    username: str,
    password: str,
    onvif_url: str,
    direction: str,
    speed: float = 0.45,
    *,
    safety_timeout: float = 1.2,
) -> str:
    """Start a bounded ONVIF move suitable for press-and-hold GUI controls.

    The command carries a short device-side timeout. The GUI renews it while
    the button remains pressed and sends Stop on release. If the GUI or network
    disappears, the camera still stops when the timeout expires.
    """
    context = discover_onvif_ptz_context(ip, username, password, onvif_url)
    continuous_move(
        context, username, password, direction, speed,
        timeout_seconds=max(0.35, min(float(safety_timeout), 1.5)),
    )
    return f"PTZ ONVIF contínuo: {direction}"


def pulse_move(
    ip: str,
    username: str,
    password: str,
    onvif_url: str,
    direction: str,
    speed: float = 0.45,
    duration: float = 0.32,
) -> str:
    """Resolve ONVIF PTZ, move briefly, then stop. Suitable for GUI button taps."""
    context = discover_onvif_ptz_context(ip, username, password, onvif_url)
    try:
        continuous_move(context, username, password, direction, speed, timeout_seconds=max(duration + 0.20, 0.35))
        sleep(max(0.08, min(float(duration), 1.0)))
    finally:
        try:
            stop(context, username, password)
        except Exception:
            # ContinuousMove carries a bounded Timeout, so failed Stop is still safe.
            pass
    return f"PTZ ONVIF: {direction}"


def stop_device(ip: str, username: str, password: str, onvif_url: str) -> str:
    context = discover_onvif_ptz_context(ip, username, password, onvif_url)
    stop(context, username, password)
    return "PTZ ONVIF: stop"


def start_move_provider(
    ip: str,
    username: str,
    password: str,
    onvif_url: str,
    direction: str,
    speed: float = 0.45,
    *,
    backend: str = "onvif",
    safety_timeout: float = 1.2,
) -> str:
    """Start PTZ through the provider-selected local backend."""
    backend = str(backend or "").lower()
    if backend not in {"onvif", "dvrip"}:
        raise ValueError("Backend PTZ indisponível")
    if backend == "dvrip":
        from .xm_dvrip import dvrip_ptz_start
        return dvrip_ptz_start(ip, username, password, direction, speed)
    return start_move(ip, username, password, onvif_url, direction, speed, safety_timeout=safety_timeout)


def stop_device_provider(
    ip: str,
    username: str,
    password: str,
    onvif_url: str,
    *,
    backend: str = "onvif",
    direction: str = "",
    speed: float = 0.45,
) -> str:
    backend = str(backend or "").lower()
    if backend not in {"onvif", "dvrip"}:
        raise ValueError("Backend PTZ indisponível")
    if backend == "dvrip":
        from .xm_dvrip import dvrip_ptz_stop
        return dvrip_ptz_stop(ip, username, password, direction, speed)
    return stop_device(ip, username, password, onvif_url)


def pulse_move_provider(
    ip: str,
    username: str,
    password: str,
    onvif_url: str,
    direction: str,
    speed: float = 0.45,
    duration: float = 0.32,
    *,
    backend: str = "onvif",
) -> str:
    backend = str(backend or "").lower()
    if backend not in {"onvif", "dvrip"}:
        raise ValueError("Backend PTZ indisponível")
    if backend == "dvrip":
        from .xm_dvrip import dvrip_ptz_start, dvrip_ptz_stop
        try:
            dvrip_ptz_start(ip, username, password, direction, speed)
            sleep(max(0.08, min(float(duration), 1.0)))
        finally:
            try:
                dvrip_ptz_stop(ip, username, password, direction, speed)
            except Exception:
                pass
        return f"PTZ DVRIP/XM: {direction}"
    return pulse_move(ip, username, password, onvif_url, direction, speed, duration)

from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional

class DeviceKind(StrEnum):
    CAMERA = "camera"
    DVR = "dvr"
    NVR = "nvr"
    XVR = "xvr"
    UNKNOWN = "unknown"

class DeviceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"

@dataclass(slots=True)
class Device:
    id: Optional[int] = None
    site_id: Optional[int] = None
    name: str = "Equipamento"
    ip: str = ""
    port: Optional[int] = None
    mac: str = ""
    manufacturer: str = ""
    model: str = ""
    firmware: str = ""
    serial: str = ""
    uuid: str = ""
    kind: DeviceKind = DeviceKind.UNKNOWN
    provider: str = "generic"
    status: DeviceStatus = DeviceStatus.UNKNOWN
    onvif_url: str = ""
    rtsp_url: str = ""
    web_url: str = ""
    metadata: dict = field(default_factory=dict)

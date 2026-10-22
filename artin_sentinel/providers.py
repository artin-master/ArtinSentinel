from __future__ import annotations
from .domain import Device, DeviceKind
from .akdb import best_profile, routing_kind_for_profile


class DeviceProvider:
    name = "generic"
    def score(self, device: Device) -> int:
        return 1
    def enrich(self, device: Device) -> Device:
        return device


class IntelbrasProvider(DeviceProvider):
    name = "intelbras"
    def score(self, device):
        text = f"{device.manufacturer} {device.model} {' '.join(device.metadata.get('scopes', []))} {' '.join(device.metadata.get('evidence', []))}".lower()
        ports = device.metadata.get("open_ports", [])
        if any(token in text for token in ("vipc 1230 d g2", "vipc-1230-d-g2", "vipc1230dg2")):
            return 115
        if "intelbras" in text or any(t in text for t in ("mhdx", " nvd", " vip")):
            return 100
        return 45 if 37777 in ports else 0


class IntelbrasMiboProvider(DeviceProvider):
    name = "intelbras-mibo"
    def score(self, device):
        text = f"{device.manufacturer} {device.model} {' '.join(device.metadata.get('evidence', []))}".lower()
        if "mibo" in text:
            return 110
        if device.kind == DeviceKind.CAMERA and device.manufacturer.lower() == "intelbras":
            return 75
        return 0


class HikvisionProvider(DeviceProvider):
    name = "hikvision"
    def score(self, device):
        text = f"{device.manufacturer} {device.model} {' '.join(device.metadata.get('scopes', []))} {' '.join(device.metadata.get('evidence', []))}".lower()
        ports = set(device.metadata.get("open_ports", []))
        score = 0
        if any(token in text for token in ("ds-7216hghi-f1", "ds 7216hghi f1", "7216hghi")):
            score += 115
        elif "hikvision" in text or "dvrdvs-webs" in text or "hikvision-webs" in text:
            score += 100
        if 8000 in ports:
            score += 55
        if 554 in ports and 80 in ports and 8000 in ports:
            score += 20
        return min(score, 115)


class JFLProvider(DeviceProvider):
    name = "jfl"
    def score(self, device):
        text = f"{device.manufacturer} {device.model} {' '.join(device.metadata.get('evidence', []))}".lower()
        return 105 if "jfl" in text else 0


class AitekProvider(DeviceProvider):
    name = "aitek"
    def score(self, device):
        text = f"{device.manufacturer} {device.model} {' '.join(device.metadata.get('evidence', []))}".lower()
        return 105 if "aitek" in text else 0


class ITBlueProvider(DeviceProvider):
    name = "it-blue"
    def score(self, device):
        text = f"{device.manufacturer} {device.model} {' '.join(device.metadata.get('evidence', []))}".lower()
        ports = set(device.metadata.get("open_ports", []))
        if "it-blue" in text or "it blue" in text:
            return 105
        if any(token in text for token in ("x3-we2q", "xm535d1", "000a06cd", "gk7202v300")):
            return 95
        if "web viewer" in text and 34567 in ports and 554 in ports:
            return 65
        return 0


class GenericONVIFProvider(DeviceProvider):
    name = "generic-onvif"
    def score(self, device):
        return 25 if device.onvif_url else 1


PROVIDERS = [
    IntelbrasMiboProvider(), IntelbrasProvider(), HikvisionProvider(), JFLProvider(),
    AitekProvider(), ITBlueProvider(), GenericONVIFProvider()
]


def pick_provider(device: Device) -> Device:
    provider = max(PROVIDERS, key=lambda item: item.score(device))
    device.provider = provider.name
    # Store the AKDB match as explainable metadata. Do not overwrite an explicit
    # manufacturer/model just because a compatibility profile matched.
    text = f"{device.manufacturer} {device.model} {' '.join(device.metadata.get('evidence', []))}"
    match = best_profile(text=text, ports=device.metadata.get("open_ports", []), manufacturer=device.manufacturer)
    if match:
        confidence, profile = match
        device.metadata["akdb_profile"] = profile.key
        device.metadata["identity_confidence"] = confidence
        device.metadata["protocol_family"] = profile.protocol_family
        device.metadata["akdb_validation"] = profile.validation
        if not device.manufacturer and confidence >= 75:
            device.manufacturer = profile.manufacturer
        if device.kind == DeviceKind.UNKNOWN:
            routed = routing_kind_for_profile(profile.key)
            if routed != "unknown" and confidence >= profile.confidence_floor:
                try:
                    device.kind = DeviceKind(routed)
                except ValueError:
                    pass
    return provider.enrich(device)


def classify_from_scopes(scopes: list[str]) -> tuple[DeviceKind, str, str]:
    joined = " ".join(scopes).lower()
    manufacturer = ""
    model = ""

    for scope in scopes:
        low = scope.lower()
        if "/manufacturer/" in low:
            manufacturer = scope.rsplit("/", 1)[-1].replace("%20", " ")
        if "/model/" in low:
            model = scope.rsplit("/", 1)[-1].replace("%20", " ")

    if any(token in joined for token in ("networkvideorecorder", "/nvr")):
        kind = DeviceKind.NVR
    elif any(token in joined for token in ("digitalvideorecorder", "/dvr")):
        kind = DeviceKind.DVR
    elif "video_encoder" in joined:
        kind = DeviceKind.XVR
    elif any(token in joined for token in ("network_video_transmitter", "video_source", "camera", "ipc")):
        kind = DeviceKind.CAMERA
    else:
        kind = DeviceKind.UNKNOWN

    return kind, manufacturer, model

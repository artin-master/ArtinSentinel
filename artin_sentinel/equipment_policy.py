"""Equipment onboarding policy used by the unified add/edit flow."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EquipmentAccessPolicy:
    provider: str
    label: str
    show_hik_sdk: bool = False
    show_intelbras_sdk: bool = False
    show_onvif: bool = False
    allow_intelbras_cloud: bool = False
    sdk_port: int | None = None
    rtsp_port: int = 554
    web_port: int = 80
    description: str = ""


def access_policy(manufacturer: str, kind: str) -> EquipmentAccessPolicy:
    brand=(manufacturer or "").strip().casefold()
    kind=(kind or "unknown").strip().casefold()
    recorder=kind in {"dvr","nvr","xvr"}
    if brand in {"hikvision","hilook","hik vision"}:
        return EquipmentAccessPolicy(
            provider="hikvision", label="Hikvision",
            show_hik_sdk=recorder, show_onvif=not recorder,
            sdk_port=8000 if recorder else None,
            description=(
                "Hikvision: HCNetSDK/ISAPI/RTSP para gravadores."
                if recorder else "Hikvision câmera: ONVIF/RTSP; SDK somente quando homologado."
            ),
        )
    if brand in {"intelbras","dahua","intelbras/dahua"}:
        intelbras=brand=="intelbras"
        return EquipmentAccessPolicy(
            provider="intelbras", label="Intelbras" if intelbras else "Dahua",
            show_intelbras_sdk=recorder, show_onvif=not recorder,
            allow_intelbras_cloud=bool(intelbras and recorder),
            sdk_port=37777 if recorder else None,
            description=(
                "Intelbras/Dahua: NetSDK/HTTP/RTSP para gravadores."
                if recorder else "Câmera Intelbras/Dahua: ONVIF/RTSP e provider homologado."
            ),
        )
    if brand in {"jfl"}:
        return EquipmentAccessPolicy(
            provider="hikvision", label="JFL / compatível Hikvision",
            show_hik_sdk=recorder, show_onvif=not recorder,
            sdk_port=8000 if recorder else None,
            description="JFL: compatibilidade Hikvision somente conforme perfil/AKDB e teste real.",
        )
    return EquipmentAccessPolicy(
        provider="generic", label="Genérico / OEM",
        show_onvif=True,
        description="Genérico/OEM: ONVIF/RTSP. SDK proprietário fica bloqueado até identificar fabricante/modelo.",
    )


def enabled_access_sections(manufacturer: str, kind: str) -> dict[str,bool]:
    p=access_policy(manufacturer,kind)
    return {
        "credentials": True,
        "web": True,
        "rtsp": True,
        "onvif": p.show_onvif,
        "hik_sdk": p.show_hik_sdk,
        "intelbras_sdk": p.show_intelbras_sdk,
        "intelbras_cloud": p.allow_intelbras_cloud,
    }

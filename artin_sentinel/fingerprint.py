from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from artin_akdb import best_knowledge_match, match_knowledge
from .akdb import profile_by_stable_id, routing_kind_for_profile
from .akdb_runtime import effective_core_records
from .domain import Device, DeviceKind
from artin_akdb.brands import canonical_manufacturer


AUTO_APPLY_THRESHOLD = 70
CANDIDATE_THRESHOLD = 35


def _kind_from_canonical(canonical: str) -> DeviceKind:
    canonical = str(canonical or "unknown").strip().lower()
    if canonical.startswith("camera"):
        return DeviceKind.CAMERA
    if canonical == "dvr":
        return DeviceKind.DVR
    if canonical == "nvr":
        return DeviceKind.NVR
    if canonical == "xvr":
        return DeviceKind.XVR
    return DeviceKind.UNKNOWN


def _protocols_for(device: Device) -> list[str]:
    ports = {int(p) for p in (device.metadata.get("open_ports") or []) if str(p).isdigit()}
    out: list[str] = []
    if device.rtsp_url or 554 in ports:
        out.append("rtsp")
    if device.onvif_url:
        out.append("onvif")
    if device.web_url or ports.intersection({80, 443, 8080}):
        out.append("http")
    if 8000 in ports:
        out.append("hikvision-service-8000")
    if 34567 in ports:
        out.append("xm-dvrip-34567")
    if 37777 in ports:
        out.append("intelbras-dahua-service-37777")
    return out


def _text_for(device: Device) -> str:
    metadata = device.metadata or {}
    values = [
        device.name, device.manufacturer, device.model, device.firmware,
        " ".join(str(x) for x in (metadata.get("evidence") or [])),
        " ".join(str(x) for x in (metadata.get("scopes") or [])),
        str(metadata.get("http_server") or ""),
        str(metadata.get("protocol_family") or ""),
    ]
    return "\n".join(v for v in values if v)


@dataclass(frozen=True, slots=True)
class FingerprintDecision:
    stable_id: str = ""
    confidence: int = 0
    canonical_type: str = "unknown"
    subtype: str = ""
    manufacturer: str = ""
    model: str = ""
    provider: str = "generic"
    profile_key: str = ""
    validation_status: str = "unknown"
    reasons: tuple[str, ...] = ()
    preferred_strategies: tuple[str, ...] = ()
    avoid_strategies: tuple[str, ...] = ()
    negative_knowledge: tuple[str, ...] = ()
    candidate: bool = False
    auto_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "confidence": int(self.confidence),
            "canonical_type": self.canonical_type,
            "subtype": self.subtype,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "provider": self.provider,
            "profile_key": self.profile_key,
            "validation_status": self.validation_status,
            "reasons": list(self.reasons),
            "preferred_strategies": list(self.preferred_strategies),
            "avoid_strategies": list(self.avoid_strategies),
            "negative_knowledge": list(self.negative_knowledge),
            "candidate": bool(self.candidate),
            "auto_applied": bool(self.auto_applied),
        }


def evidence_for_device(device: Device) -> dict[str, Any]:
    identifiers: list[str] = []
    if device.model:
        identifiers.append("model:" + str(device.model).strip().lower())
    if device.uuid:
        identifiers.append("uuid-present")  # value itself never enters shared AKDB matching/export
    return {
        "manufacturer": canonical_manufacturer(device.manufacturer),
        "model": device.model,
        "text": _text_for(device),
        "identifiers": identifiers,
        "fingerprints": device.metadata.get("fingerprints") or [],
        "protocols": _protocols_for(device),
    }


def identify_device(device: Device) -> FingerprintDecision:
    evidence = evidence_for_device(device)
    matches = match_knowledge(evidence, records=effective_core_records())
    if not matches:
        return FingerprintDecision(candidate=True)
    top = matches[0]
    if top.confidence < CANDIDATE_THRESHOLD:
        return FingerprintDecision(candidate=True)
    record = top.record
    profile = profile_by_stable_id(record.stable_id)
    provider = profile.provider if profile is not None else (device.provider or "generic")
    profile_key = profile.key if profile is not None else (record.legacy_keys[0] if record.legacy_keys else "")
    from artin_akdb.brands import normalize,canonical_manufacturer
    generic={'','unknown','oem','generic','genérico','não identificado','desconhecido'}
    brand_conflict=(normalize(canonical_manufacturer(device.manufacturer)) not in generic
        and not record.manufacturer.casefold().startswith('oem')
        and normalize(canonical_manufacturer(device.manufacturer))!=normalize(canonical_manufacturer(record.manufacturer)))
    ambiguous=len(matches)>1 and matches[1].confidence==top.confidence and top.confidence>=AUTO_APPLY_THRESHOLD
    auto = top.confidence >= AUTO_APPLY_THRESHOLD and not brand_conflict and not ambiguous
    candidate = not auto or record.validation_status not in {"homologated", "documented", "field-validated"}
    return FingerprintDecision(
        stable_id=record.stable_id,
        confidence=int(top.confidence),
        canonical_type=record.canonical_type,
        subtype=record.subtype,
        manufacturer=record.manufacturer,
        model=record.model,
        provider=provider,
        profile_key=profile_key,
        validation_status=record.validation_status,
        reasons=tuple(top.reasons) + (('Conflito entre fabricante observado e perfil AKDB',) if brand_conflict else ()) + (('Mais de um perfil com a mesma confiança; revisar',) if ambiguous else ()),
        preferred_strategies=tuple(record.preferred_strategies),
        avoid_strategies=tuple(record.avoid_strategies),
        negative_knowledge=tuple(record.negative_knowledge),
        candidate=candidate,
        auto_applied=auto,
    )


def apply_device_fingerprint(device: Device) -> FingerprintDecision:
    """Apply an AKDB decision to a transient discovery object.

    Manual overrides live only in the persisted DB; a transient discovery object
    has no operator lock.  Only high-confidence matches can change routing type.
    Lower-confidence results are carried as candidate metadata for review.
    """
    from datetime import datetime, timezone
    observed={key:str(getattr(device,key,'') or '') for key in ('manufacturer','model','kind','provider')}
    decision = identify_device(device)
    metadata = dict(device.metadata or {})
    metadata['identity_evidence_v1']={
        'observed_at':datetime.now(timezone.utc).isoformat(),
        'observed':observed,
        'sources':[str(v)[:100] for v in (metadata.get('discovery_sources') or [])[:16]],
        'akdb':{'stable_id':decision.stable_id,'confidence':decision.confidence,
                'applied':decision.auto_applied,'reasons':list(decision.reasons)}}
    conflicts=[r for r in decision.reasons if r.startswith(('Conflito','Mais de um perfil'))]
    metadata['identity_conflicts']=conflicts
    if decision.stable_id:
        profile=profile_by_stable_id(decision.stable_id)
        metadata['registration_suggestions']={
            'source':'AKDB','stable_id':decision.stable_id,'confidence':decision.confidence,
            'requires_verification':True,'applied':decision.auto_applied,
            'manufacturer':decision.manufacturer,'model':decision.model,'canonical_type':decision.canonical_type,
            'provider':decision.provider,
            'ports_candidates':list(profile.ports_any) if profile else [],
            'channel_capacity':int(profile.max_total_channels or profile.max_analog_channels+profile.max_ip_channels) if profile else 0}

    metadata["akdb_stable_id"] = decision.stable_id
    metadata["akdb_confidence"] = decision.confidence
    metadata["akdb_reasons"] = list(decision.reasons)
    metadata["canonical_type"] = decision.canonical_type
    metadata["device_subtype"] = decision.subtype
    metadata["homologation_status"] = decision.validation_status if decision.stable_id else "candidate"
    metadata["homologation_candidate"] = bool(decision.candidate or not decision.stable_id)
    metadata["preferred_strategies"] = list(decision.preferred_strategies)
    metadata["avoid_strategies"] = list(decision.avoid_strategies)
    metadata["negative_knowledge"] = list(decision.negative_knowledge)
    if decision.profile_key:
        metadata["akdb_profile"] = decision.profile_key
    if decision.auto_applied:
        metadata["identity_confidence"] = max(int(metadata.get("identity_confidence") or 0), decision.confidence)
        if decision.manufacturer and (not device.manufacturer or device.manufacturer.casefold() in {"oem", "unknown"}):
            # OEM platform records must not invent a commercial manufacturer.
            if not decision.manufacturer.casefold().startswith("oem"):
                device.manufacturer = decision.manufacturer
        if decision.model and (not device.model or device.model.casefold() in {"web viewer", "ip camera", "ipc"}):
            device.model = decision.model
        kind = _kind_from_canonical(decision.canonical_type)
        if kind != DeviceKind.UNKNOWN:
            device.kind = kind
        if decision.provider and decision.provider != "generic":
            device.provider = decision.provider
    device.metadata = metadata
    return decision


def fingerprint_summary(device: Device) -> str:
    decision = identify_device(device)
    if not decision.stable_id:
        return "Novo equipamento • candidato à homologação"
    subtype = f" / {decision.subtype}" if decision.subtype else ""
    return f"AKDB {decision.confidence}% • {decision.canonical_type}{subtype} • {decision.validation_status}"

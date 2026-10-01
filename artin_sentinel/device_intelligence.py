from __future__ import annotations

"""Resolve the operational device identity without destroying discovery evidence.

0.2.14 makes the precedence explicit:
operator override -> exact AKDB profile -> current stored kind -> detected kind.
The result is used only for routing/UI decisions.  Raw detected evidence remains
stored separately in SQLite.
"""

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .akdb import canonical_type_label, profile_by_key, routing_kind_for_profile, reconcile_operational_profile_key


LEGACY_KIND_LABELS = {
    "camera": "Câmera IP",
    "dvr": "DVR",
    "nvr": "NVR",
    "xvr": "DVR / Multi HD",
    "unknown": "Não identificado",
}


@dataclass(frozen=True, slots=True)
class OperationalIdentity:
    kind: str
    canonical_type: str
    source: str
    profile_key: str = ""

    @property
    def kind_label(self) -> str:
        return LEGACY_KIND_LABELS.get(self.kind, self.kind or "Não identificado")

    @property
    def canonical_label(self) -> str:
        return canonical_type_label(self.canonical_type)


def _value(row: Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        if isinstance(row, Mapping):
            value = row.get(key, default)
        else:
            value = getattr(row, key, default)
    return default if value is None else value


def _metadata(row: Any) -> dict:
    raw = _value(row, "metadata_json", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _canonical_from_kind(kind: str) -> str:
    kind = str(kind or "unknown").strip().lower()
    return kind if kind in {"dvr", "nvr", "xvr"} else ("camera" if kind == "camera" else "unknown")


def resolve_operational_identity(row: Any) -> OperationalIdentity:
    """Return the type used for protocol routing and operator-facing status.

    A persisted manual override always wins.  The AKDB exact profile is next,
    because a model-specific profile is stronger than generic discovery scope
    heuristics.  Ambiguous provider-wide profiles never force a type.
    """
    metadata = _metadata(row)
    profile_key = str(metadata.get("akdb_profile") or "")
    identity_text = " ".join(
        str(_value(row, key, "") or "")
        for key in ("name", "model", "detected_name", "detected_model", "manufacturer", "detected_manufacturer")
    )
    profile_key = reconcile_operational_profile_key(
        profile_key=profile_key, provider=str(_value(row, "provider", "") or ""), identity_text=identity_text
    )

    manual_kind = str(_value(row, "manual_kind", "") or "").strip().lower()
    locked = bool(int(_value(row, "identity_locked", 0) or 0))
    if manual_kind:
        return OperationalIdentity(manual_kind, _canonical_from_kind(manual_kind), "operator", profile_key)
    if locked:
        stored = str(_value(row, "kind", "unknown") or "unknown").strip().lower()
        return OperationalIdentity(stored, _canonical_from_kind(stored), "operator-legacy", profile_key)

    if profile_key:
        routed = routing_kind_for_profile(profile_key)
        profile = profile_by_key(profile_key)
        if routed != "unknown" and profile is not None:
            return OperationalIdentity(routed, profile.canonical_type, "akdb", profile_key)

    stored = str(_value(row, "kind", "unknown") or "unknown").strip().lower()
    if stored in {"camera", "dvr", "nvr", "xvr"}:
        return OperationalIdentity(stored, _canonical_from_kind(stored), "stored", profile_key)

    detected = str(_value(row, "detected_kind", "unknown") or "unknown").strip().lower()
    if detected in {"camera", "dvr", "nvr", "xvr"}:
        return OperationalIdentity(detected, _canonical_from_kind(detected), "detected", profile_key)

    return OperationalIdentity("unknown", "unknown", "unknown", profile_key)



def recorder_provider_hint(row: Any, identity: OperationalIdentity | None = None) -> str:
    """Choose a recorder protocol family without confusing unknown recorders with Dahua.

    An explicit operator-selected protocol wins, followed by an exact AKDB
    profile, detected provider and manufacturer evidence. Returns ``generic``
    when there is not enough evidence.
    """
    identity = identity or resolve_operational_identity(row)
    selected_protocol = str(_metadata(row).get("recorder_protocol") or "").strip().lower()
    if selected_protocol in {"intelbras", "hikvision"}:
        return selected_protocol
    if identity.profile_key:
        profile = profile_by_key(identity.profile_key)
        if profile is not None and profile.provider in {"hikvision", "jfl", "intelbras"}:
            return profile.provider
    provider = str(_value(row, "provider", "") or "").strip().lower()
    detected_provider = str(_value(row, "detected_provider", "") or "").strip().lower()
    for value in (provider, detected_provider):
        if value in {"hikvision", "jfl", "intelbras"}:
            return value
    text = " ".join(
        str(_value(row, key, "") or "")
        for key in ("manufacturer", "model", "detected_manufacturer", "detected_model", "name")
    ).lower()
    if "hikvision" in text or "ds-" in text:
        return "hikvision"
    if "jfl" in text:
        return "jfl"
    if any(token in text for token in ("intelbras", "mhdx", "nvd")):
        return "intelbras"
    return "generic"

def routing_explanation(identity: OperationalIdentity) -> str:
    source = {
        "operator": "override manual",
        "operator-legacy": "override manual legado",
        "akdb": "AKDB",
        "stored": "identidade persistida",
        "detected": "detecção automática",
        "unknown": "sem evidência suficiente",
    }.get(identity.source, identity.source)
    profile = f" • {identity.profile_key}" if identity.profile_key else ""
    return f"{identity.kind_label} • origem: {source}{profile}"

def device_visual_name(device) -> str:
    """Prefer an operator name; otherwise show the best known model.

    Discovery historically filled ``name`` with generic labels such as
    ``Hikvision``, ``Intelbras`` or ``IP CAMERA``. Those are useful evidence,
    but poor labels in a VMS tree. Until an explicit user-name flag is migrated
    into the DB, meaningful custom names win and generic labels fall back to
    the model identity.
    """
    def value(key: str, default=""):
        try:
            return str(device[key] or default).strip()
        except Exception:
            return str(default).strip()

    name = value("name")
    manufacturer = value("manufacturer") or value("detected_manufacturer")
    model = value("model") or value("detected_model")
    generic = {
        "camera", "câmera", "camera ip", "câmera ip", "ip camera", "web viewer",
        "dvr", "nvr", "xvr", "gravador", "intelbras", "hikvision", "aitek",
        "it-blue", "it blue", "mibocam", "speed dome", "speeddome",
    }
    folded = name.casefold()
    manufacturer_folded = manufacturer.casefold()
    generic_family_label = bool(
        manufacturer_folded
        and manufacturer_folded in folded
        and any(token in folded for token in ("camera", "câmera", "speed dome", "speeddome", "ball", "dvr", "nvr", "xvr"))
    )
    is_generic = (
        not name
        or folded in generic
        or (manufacturer_folded and folded == manufacturer_folded)
        or folded.startswith("ip camera")
        or folded.startswith("câmera ip")
        or generic_family_label
    )
    if name and not is_generic:
        return name
    if model and (not manufacturer or model.casefold() != manufacturer.casefold()):
        return model
    if name:
        return name
    if manufacturer:
        return manufacturer
    return value("ip", "Equipamento")

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Mapping


SCHEMA_VERSION = 2
CORE_VERSION = "0.2.0"
CORE_REVISION = 13

VALIDATION_STATES = {
    "unknown",
    "detected",
    "documented",
    "tested",
    "field-detected",
    "field-identified",
    "field-identified-cloud-only",
    "field-validated",
    "candidate",
    "in-review",
    "partially-homologated",
    "homologated",
    "rejected",
}

HOMOLOGATION_STATES = {
    "unknown",
    "candidate",
    "in-review",
    "partially-homologated",
    "homologated",
    "rejected",
}

EVIDENCE_LAYERS = {
    "automatic-detection",
    "field-test",
    "homologation-candidate",
    "homologated",
    "local-override",
}


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    """Domain-neutral identity and knowledge shared by Artin applications.

    App-specific details (RTSP paths, SMART quirks, RouterOS fields, etc.) do
    not belong here. They are attached through domain extensions using the
    same stable_id.

    ``subtype`` and the strategy fields are intentionally generic. They let the
    shared AKDB answer not only *what* a device is, but also which discovery
    family an Artin app should prefer or avoid.
    """

    stable_id: str
    manufacturer: str
    canonical_type: str
    family: str = ""
    model: str = ""
    variant: str = ""
    subtype: str = ""
    aliases: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()
    fingerprints: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    protocols: tuple[str, ...] = ()
    preferred_strategies: tuple[str, ...] = ()
    avoid_strategies: tuple[str, ...] = ()
    negative_knowledge: tuple[str, ...] = ()
    validation_status: str = "detected"
    provenance: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    revision: int = 1
    legacy_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = SCHEMA_VERSION
        data["core_version"] = CORE_VERSION
        data["core_revision"] = CORE_REVISION
        return data


@dataclass(frozen=True, slots=True)
class DomainExtension:
    stable_id: str
    domain: str
    extension_schema: str
    revision: int = 1
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "domain": self.domain,
            "extension_schema": self.extension_schema,
            "revision": int(self.revision),
            "payload": dict(self.payload),
        }

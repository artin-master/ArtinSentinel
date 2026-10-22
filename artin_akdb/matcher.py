from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Any

from .catalog import CORE_RECORDS
from .models import KnowledgeRecord


def _norm(value: str) -> str:
    value = str(value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _tokens(values: Iterable[str]) -> set[str]:
    return {_norm(v) for v in values if _norm(v)}


@dataclass(frozen=True, slots=True)
class MatchResult:
    record: KnowledgeRecord
    confidence: int
    reasons: tuple[str, ...]

    @property
    def stable_id(self) -> str:
        return self.record.stable_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.record.stable_id,
            "manufacturer": self.record.manufacturer,
            "family": self.record.family,
            "model": self.record.model,
            "variant": self.record.variant,
            "canonical_type": self.record.canonical_type,
            "subtype": self.record.subtype,
            "confidence": int(self.confidence),
            "reasons": list(self.reasons),
            "validation_status": self.record.validation_status,
            "preferred_strategies": list(self.record.preferred_strategies),
            "avoid_strategies": list(self.record.avoid_strategies),
            "protocols": list(self.record.protocols),
        }


def match_knowledge(evidence: Mapping[str, Any], *, records: Iterable[KnowledgeRecord] = CORE_RECORDS) -> list[MatchResult]:
    """Match normalized discovery evidence against the shared AKDB Core.

    The scorer deliberately gives the highest weight to exact self-reported
    model/identifier values. Manufacturer-only matches stay weak and therefore
    cannot force a device type by themselves.
    """
    manufacturer = _norm(evidence.get("manufacturer", ""))
    model = _norm(evidence.get("model", ""))
    family = _norm(evidence.get("family", ""))
    variant = _norm(evidence.get("variant", ""))
    text = _norm(evidence.get("text", ""))
    identifiers = _tokens(evidence.get("identifiers", ()) or ())
    fingerprints = _tokens(evidence.get("fingerprints", ()) or ())
    protocols = _tokens(evidence.get("protocols", ()) or ())
    corpus = " ".join(v for v in (manufacturer, model, family, variant, text) if v)

    results: list[MatchResult] = []
    for record in records:
        score = 0
        reasons: list[str] = []
        rec_manufacturer = _norm(record.manufacturer)
        rec_model = _norm(record.model)
        rec_family = _norm(record.family)
        rec_variant = _norm(record.variant)

        if manufacturer and rec_manufacturer and manufacturer == rec_manufacturer:
            score += 20
            reasons.append("fabricante coincide")

        # A model value returned by firmware/HTTP/ONVIF is the strongest normal
        # field evidence. Generic family labels are intentionally excluded.
        if model and rec_model and model == rec_model:
            score += 70
            reasons.append("modelo exato reportado")
        elif rec_model and rec_model not in {"family", "generic", "unknown"} and rec_model in corpus:
            score += 48
            reasons.append("modelo encontrado nas evidências")

        aliases = _tokens(record.aliases)
        if model and model in aliases:
            score += 60
            reasons.append("alias de modelo exato")
        elif aliases.intersection(_tokens((model, text))):
            score += 35
            reasons.append("alias AKDB observado")
        else:
            alias_hit = next((alias for alias in aliases if alias and alias in corpus), "")
            if alias_hit:
                score += 30
                reasons.append(f"alias observado: {alias_hit}")

        if family and rec_family and family == rec_family:
            score += 18
            reasons.append("família coincide")
        elif rec_family and rec_family in corpus and rec_family != rec_model:
            score += 12
            reasons.append("família observada")

        # Variant is supporting evidence only: many OEM platforms are shared by
        # multiple commercial models and must not be promoted from this alone.
        if variant and rec_variant and variant == rec_variant:
            score += 12
            reasons.append("variante coincide")
        elif rec_variant and rec_variant in corpus:
            score += 8
            reasons.append("variante observada")

        record_ids = _tokens(record.identifiers)
        id_hit = record_ids.intersection(identifiers)
        if id_hit:
            score += min(70, 45 + 10 * (len(id_hit) - 1))
            reasons.append("identificador forte coincide")

        record_fp = _tokens(record.fingerprints)
        fp_hit = record_fp.intersection(fingerprints)
        if fp_hit:
            score += min(45, 25 + 5 * (len(fp_hit) - 1))
            reasons.append("fingerprint técnico coincide")

        protocol_hit = _tokens(record.protocols).intersection(protocols)
        if protocol_hit:
            score += min(15, len(protocol_hit) * 5)
            reasons.append("protocolos compatíveis: " + ", ".join(sorted(protocol_hit)))

        if score:
            results.append(MatchResult(record, min(100, score), tuple(reasons)))

    results.sort(key=lambda item: (item.confidence, item.record.revision), reverse=True)
    return results


def best_knowledge_match(evidence: Mapping[str, Any], *, minimum: int = 0) -> MatchResult | None:
    matches = match_knowledge(evidence)
    if not matches or matches[0].confidence < int(minimum):
        return None
    return matches[0]

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from .catalog import CORE_RECORDS
from .models import CORE_VERSION, CORE_REVISION, SCHEMA_VERSION, DomainExtension, KnowledgeRecord

BUNDLE_SCHEMA = "artin-akdb-bundle-v1"
APPLICATION_DOMAINS = ("sentinel", "netlens", "rescnow")


def build_bundle(
    *,
    records: Iterable[KnowledgeRecord] = CORE_RECORDS,
    extensions: Iterable[DomainExtension] = (),
) -> dict:
    record_rows = [record.to_dict() for record in records]
    extension_rows = [extension.to_dict() for extension in extensions]
    return {
        "schema": BUNDLE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "core_version": CORE_VERSION,
        "core_revision": CORE_REVISION,
        "applications": list(APPLICATION_DOMAINS),
        "records": record_rows,
        "extensions": extension_rows,
    }


def validate_bundle(bundle: dict) -> list[str]:
    errors: list[str] = []
    if bundle.get("schema") != BUNDLE_SCHEMA:
        errors.append("unsupported bundle schema")
    if int(bundle.get("schema_version") or 0) != SCHEMA_VERSION:
        errors.append("unsupported AKDB schema version")
    records = bundle.get("records") or []
    ids = [str(row.get("stable_id") or "") for row in records]
    if any(not stable_id for stable_id in ids):
        errors.append("record without stable_id")
    if len(ids) != len(set(ids)):
        errors.append("duplicate stable_id")
    known = set(ids)
    for extension in bundle.get("extensions") or []:
        stable_id = str(extension.get("stable_id") or "")
        domain = str(extension.get("domain") or "")
        if stable_id not in known:
            errors.append(f"extension references unknown stable_id: {stable_id}")
        if domain not in APPLICATION_DOMAINS:
            errors.append(f"unsupported extension domain: {domain}")
    return errors


def bundle_fingerprint(bundle: dict) -> str:
    normalized = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def write_bundle(path: str | Path, bundle: dict) -> Path:
    errors = validate_bundle(bundle)
    if errors:
        raise ValueError("invalid AKDB bundle: " + "; ".join(errors))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out

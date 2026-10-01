from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from typing import Any, Mapping

from .exchange import validate_bundle
from .models import DomainExtension, KnowledgeRecord

AKDB_MANIFEST_SCHEMA = "artin-akdb-manifest-v1"


def sha256_json(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_manifest(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != AKDB_MANIFEST_SCHEMA:
        errors.append("unsupported AKDB manifest schema")
    try:
        release_revision = int(payload.get("release_revision") or 0)
    except Exception:
        release_revision = 0
    if release_revision <= 0:
        errors.append("invalid AKDB release_revision")
    bundle = payload.get("bundle") or {}
    if not isinstance(bundle, Mapping):
        errors.append("invalid AKDB bundle descriptor")
    else:
        url = str(bundle.get("url") or "").strip()
        inline = str(bundle.get("data_gzip_base64") or "").strip()
        digest = str(bundle.get("sha256") or "").strip().lower()
        if not url and not inline:
            errors.append("AKDB bundle URL or inline payload missing")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            errors.append("AKDB bundle sha256 invalid")
    return errors


def knowledge_record_from_dict(payload: Mapping[str, Any]) -> KnowledgeRecord:
    allowed = {f.name for f in fields(KnowledgeRecord)}
    values = {key: payload[key] for key in allowed if key in payload}
    for key in (
        "aliases", "identifiers", "fingerprints", "capabilities", "protocols",
        "preferred_strategies", "avoid_strategies", "negative_knowledge", "provenance", "domains", "legacy_keys",
    ):
        if key in values and not isinstance(values[key], tuple):
            values[key] = tuple(values[key] or ())
    return KnowledgeRecord(**values)


def domain_extension_from_dict(payload: Mapping[str, Any]) -> DomainExtension:
    return DomainExtension(
        stable_id=str(payload.get("stable_id") or ""),
        domain=str(payload.get("domain") or ""),
        extension_schema=str(payload.get("extension_schema") or ""),
        revision=int(payload.get("revision") or 1),
        payload=dict(payload.get("payload") or {}),
    )


def bundle_delta(store, bundle: Mapping[str, Any]) -> dict[str, int]:
    errors = validate_bundle(dict(bundle))
    if errors:
        raise ValueError("invalid AKDB bundle: " + "; ".join(errors))
    new_records = updated_records = unchanged_records = conflicts = 0
    remote_ids: set[str] = set()
    for payload in bundle.get("records") or []:
        stable_id = str(payload.get("stable_id") or "")
        remote_ids.add(stable_id)
        row = store.conn.execute(
            "SELECT revision,content_hash FROM records WHERE stable_id=?", (stable_id,)
        ).fetchone()
        if row is None:
            new_records += 1
            continue
        remote_revision = int(payload.get("revision") or 0)
        local_revision = int(row["revision"] or 0)
        digest = sha256_json(payload)
        if remote_revision > local_revision:
            updated_records += 1
        elif remote_revision == local_revision and str(row["content_hash"] or "") == digest:
            unchanged_records += 1
        elif remote_revision == local_revision:
            conflicts += 1
        else:
            unchanged_records += 1
    local_ids = {str(row["stable_id"]) for row in store.conn.execute("SELECT stable_id FROM records")}
    removed_records = len(local_ids - remote_ids)

    new_extensions = updated_extensions = unchanged_extensions = extension_conflicts = 0
    for payload in bundle.get("extensions") or []:
        stable_id = str(payload.get("stable_id") or "")
        domain = str(payload.get("domain") or "")
        row = store.conn.execute(
            "SELECT revision,extension_schema,payload_json FROM domain_extensions WHERE stable_id=? AND domain=?",
            (stable_id, domain),
        ).fetchone()
        if row is None:
            new_extensions += 1
            continue
        remote_revision = int(payload.get("revision") or 0)
        local_revision = int(row["revision"] or 0)
        remote_payload = json.dumps(dict(payload.get("payload") or {}), ensure_ascii=False, sort_keys=True)
        if remote_revision > local_revision:
            updated_extensions += 1
        elif (remote_revision == local_revision and str(row["payload_json"] or "") == remote_payload
              and str(row["extension_schema"]) == str(payload.get("extension_schema") or "")):
            unchanged_extensions += 1
        elif remote_revision == local_revision:
            extension_conflicts += 1
        else:
            unchanged_extensions += 1
    return {
        "new_records": new_records,
        "updated_records": updated_records,
        "unchanged_records": unchanged_records,
        "removed_records": removed_records,
        "conflicts": conflicts,
        "new_extensions": new_extensions,
        "updated_extensions": updated_extensions,
        "unchanged_extensions": unchanged_extensions,
        "extension_conflicts": extension_conflicts,
    }


def bundle_change_preview(store, bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Describe changes without modifying the database or exposing payload values."""
    errors = validate_bundle(dict(bundle))
    if errors:
        raise ValueError("invalid AKDB bundle: " + "; ".join(errors))
    changes: list[dict[str, Any]] = []
    for payload in bundle.get("records") or []:
        stable_id = str(payload["stable_id"])
        row = store.conn.execute(
            "SELECT revision,content_hash,payload_json FROM records WHERE stable_id=?", (stable_id,)
        ).fetchone()
        incoming_revision = int(payload.get("revision") or 0)
        if row is None:
            status, old, fields_changed = "new", 0, []
        else:
            old = int(row["revision"] or 0)
            if incoming_revision < old:
                continue  # Newer local record is preserved by the importer.
            if incoming_revision == old and str(row["content_hash"] or "") == sha256_json(payload):
                continue
            status = "updated" if incoming_revision > old else "conflict"
            previous = json.loads(row["payload_json"])
            incoming_record = json.loads(json.dumps(dict(payload), ensure_ascii=False))
            fields_changed = sorted(key for key in set(previous) | set(incoming_record)
                                    if previous.get(key) != incoming_record.get(key))
        changes.append({
            "scope": "identity", "status": status, "stable_id": stable_id,
            "label": " ".join(str(payload.get(key) or "") for key in ("manufacturer", "model")).strip() or stable_id,
            "local_revision": old, "incoming_revision": incoming_revision, "changed_fields": fields_changed,
        })
    for payload in bundle.get("extensions") or []:
        stable_id, domain = str(payload["stable_id"]), str(payload["domain"])
        row = store.conn.execute(
            "SELECT revision,extension_schema,payload_json FROM domain_extensions WHERE stable_id=? AND domain=?",
            (stable_id, domain),
        ).fetchone()
        incoming_revision = int(payload.get("revision") or 0)
        incoming = dict(payload.get("payload") or {})
        if row is None:
            status, old, fields_changed = "new", 0, []
        else:
            old = int(row["revision"] or 0)
            if incoming_revision < old:
                continue
            previous = json.loads(row["payload_json"])
            schema_changed = str(row["extension_schema"]) != str(payload.get("extension_schema") or "")
            if incoming_revision == old and not schema_changed and previous == incoming:
                continue
            status = "updated" if incoming_revision > old else "conflict"
            fields_changed = sorted(key for key in set(previous) | set(incoming) if previous.get(key) != incoming.get(key))
            if schema_changed:
                fields_changed.insert(0, "extension_schema")
        changes.append({
            "scope": "extension", "status": status, "stable_id": stable_id, "domain": domain,
            "label": f"{stable_id} • {domain}", "local_revision": old,
            "incoming_revision": incoming_revision, "changed_fields": fields_changed,
        })
    return changes

from __future__ import annotations

"""Sentinel adapter for the shared Artin AKDB core.

The shared database stores only sanitized candidate evidence.  A field result
never becomes official/homologated knowledge without review and a later AKDB
revision.
"""

from typing import Any

from artin_akdb import DomainExtension, SharedAkdbStore, record_by_legacy_key
from .akdb import public_summary, AKDB_EXTENSION_REVISIONS


def sentinel_domain_extensions() -> list[DomainExtension]:
    extensions: list[DomainExtension] = []
    for row in public_summary():
        core = record_by_legacy_key(row["key"])
        if core is None:
            continue
        payload = {
            "provider": row.get("provider", "generic"),
            "protocol_family": row.get("protocol_family", "generic"),
            "stream_count": row.get("stream_count", 0),
            "video_codecs": row.get("video_codecs", []),
            "onvif_profiles": row.get("onvif_profiles", []),
            "native_protocols": row.get("native_protocols", []),
            "audio_mode": row.get("audio_mode", "unknown"),
            "audio_codecs": row.get("audio_codecs", []),
            "talkback_protocol": row.get("talkback_protocol", ""),
            "talkback_scope": row.get("talkback_scope", "all"),
            "talkback_validation": row.get("talkback_validation", "unknown"),
            "ptz_mode": row.get("ptz_mode", "unknown"),
            "ptz_scope": row.get("ptz_scope", "all"),
            "max_analog_channels": row.get("max_analog_channels", 0),
            "max_ip_channels": row.get("max_ip_channels", 0),
        }
        if row.get("key") in {"intelbras-nvd-1416", "intelbras-nvd-1516", "intelbras-mhdx-1216"}:
            payload["max_total_channels"] = row.get("max_total_channels", 0)
        extensions.append(DomainExtension(
            stable_id=core.stable_id,
            domain="sentinel",
            extension_schema="artin-akdb-sentinel-v2",
            revision=AKDB_EXTENSION_REVISIONS.get(row.get("key"), 2),
            payload=payload,
        ))
    return extensions


def sync_shared_akdb(path=None) -> dict[str, Any]:
    with SharedAkdbStore(path) as store:
        changed = store.sync_catalog()
        for extension in sentinel_domain_extensions():
            store.sync_extension(extension)
        state = store.sync_state(domain="sentinel")
        return {
            "path": str(store.path),
            "records": store.record_count(),
            "evidence": store.evidence_count(),
            "field_reports": store.field_report_count(),
            "changed": changed,
            **state,
        }


def _candidate_payload(report: dict) -> dict:
    device = report.get("device") or {}
    discovery = report.get("discovery") or {}
    summary = report.get("summary") or {}
    # Explicit allow-list: no IP/MAC/serial/authenticated URLs/display names.
    return {
        "manufacturer": device.get("manufacturer", ""),
        "model": device.get("model", ""),
        "firmware": device.get("firmware", ""),
        "kind": device.get("kind", "unknown"),
        "canonical_type": discovery.get("canonical_type", "unknown"),
        "device_subtype": discovery.get("device_subtype", ""),
        "provider": device.get("provider", "generic"),
        "identity_confidence": int(device.get("identity_confidence") or 0),
        "open_ports": list(discovery.get("open_ports") or []),
        "onvif_present": bool(discovery.get("onvif_present")),
        "web_present": bool(discovery.get("web_present")),
        "rtsp_present": bool(discovery.get("rtsp_present")),
        "protocol_family": discovery.get("protocol_family", ""),
        "channels_saved": int(summary.get("channels_saved") or 0),
        "channels_available": int(summary.get("channels_available") or 0),
        "audio_tracks": int(summary.get("audio_tracks") or 0),
        "bidirectional_audio": int(summary.get("bidirectional_audio") or 0),
    }


def record_compatibility_candidate(report: dict, *, source_version: str, path=None) -> dict[str, Any]:
    discovery = report.get("discovery") or {}
    device = report.get("device") or {}
    legacy_key = str(discovery.get("akdb_profile") or "")
    core = record_by_legacy_key(legacy_key) if legacy_key else None
    confidence = int(device.get("identity_confidence") or 0)
    payload = _candidate_payload(report)
    with SharedAkdbStore(path) as store:
        store.sync_catalog()
        for extension in sentinel_domain_extensions():
            store.sync_extension(extension)
        evidence_id = store.record_evidence(
            app_id="artin-sentinel",
            evidence_layer="field-test",
            status="candidate",
            payload=payload,
            stable_id=core.stable_id if core else "",
            confidence=confidence,
            source_version=source_version,
        )
        report_id = store.register_field_report(
            app_id="artin-sentinel", report=report, stable_id=core.stable_id if core else ""
        )
        state = store.sync_state(domain="sentinel")
        return {
            "id": evidence_id, "report_id": report_id, "path": str(store.path),
            "stable_id": core.stable_id if core else "", "local_generation": state["local_generation"],
            "upload_pending": state["upload_pending"],
        }


def record_field_homologation_report(report: dict, *, source_version: str, path=None) -> dict[str, Any]:
    identity = report.get("identity") or {}
    stable_id = str(identity.get("stable_id") or "")
    confidence = int(identity.get("confidence") or 0)
    with SharedAkdbStore(path) as store:
        store.sync_catalog()
        for extension in sentinel_domain_extensions():
            store.sync_extension(extension)
        report_id = store.register_field_report(app_id="artin-sentinel", report=report, stable_id=stable_id)
        evidence_id = store.record_evidence(
            app_id="artin-sentinel",
            evidence_layer="homologation-candidate",
            status="candidate",
            payload={
                "report_schema": report.get("schema", ""),
                "identity": identity,
                "evidence": report.get("evidence") or {},
            },
            stable_id=stable_id,
            confidence=confidence,
            source_version=source_version,
        )
        state = store.sync_state(domain="sentinel")
        return {
            "report_id": report_id,
            "evidence_id": evidence_id,
            "path": str(store.path),
            "stable_id": stable_id,
            "local_generation": state["local_generation"],
            "upload_pending": state["upload_pending"],
        }

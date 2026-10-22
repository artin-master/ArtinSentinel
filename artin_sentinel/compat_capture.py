from __future__ import annotations

"""Credential-free compatibility capture for field testing and AKDB review.

Reports are deliberately sanitized so they can be shared back into the Artin
Sentinel project without exposing passwords, tokens or authenticated RTSP URLs.
They are evidence packages, not automatic AKDB truth: field review is still
required before a signature becomes a validated profile.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        loaded = json.loads(value or "{}")
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def sanitize_url(value: str, *, redact_host: bool = True) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parts = urlsplit(value)
    except Exception:
        return "<redacted-url>"
    host = "<device>" if redact_host else (parts.hostname or "")
    port = f":{parts.port}" if parts.port else ""
    netloc = host + port
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def _row_value(row, key, default=""):
    try:
        return row[key]
    except Exception:
        if isinstance(row, dict):
            return row.get(key, default)
        return default


def build_compatibility_report(device, channels, *, sentinel_version: str, akdb_profiles=None) -> dict:
    metadata = _json_dict(_row_value(device, "metadata_json", "{}"))
    evidence = metadata.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    open_ports = metadata.get("open_ports", [])
    if not isinstance(open_ports, list):
        open_ports = []

    channel_rows = []
    for ch in channels or []:
        channel_rows.append({
            "channel_no": int(_row_value(ch, "channel_no", 0) or 0),
            "source_name": _row_value(ch, "source_name", "") or _row_value(ch, "name", ""),
            "available": bool(_row_value(ch, "available", 0)),
            "preferred_stream": _row_value(ch, "preferred_stream", "auto") or "auto",
            "main_rtsp": sanitize_url(_row_value(ch, "main_rtsp_url", "") or _row_value(ch, "rtsp_url", "")),
            "sub_rtsp": sanitize_url(_row_value(ch, "sub_rtsp_url", "")),
            "detail": _row_value(ch, "detail", ""),
            "audio_mode": _row_value(ch, "audio_mode", "unknown") or "unknown",
            "audio_codec": _row_value(ch, "audio_codec", ""),
            "audio_sample_rate": int(_row_value(ch, "audio_sample_rate", 0) or 0),
            "audio_channels": int(_row_value(ch, "audio_channels", 0) or 0),
            "audio_detail": _row_value(ch, "audio_detail", ""),
        })

    report = {
        "schema": "artin-sentinel-compatibility-capture-v1",
        "sentinel_version": sentinel_version,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "privacy": {
            "credentials_included": False,
            "ip_redacted": True,
            "mac_redacted": True,
            "serial_redacted": True,
            "authenticated_urls_redacted": True,
        },
        "device": {
            "display_name": _row_value(device, "name", ""),
            "detected_name": _row_value(device, "detected_name", ""),
            "manufacturer": _row_value(device, "manufacturer", ""),
            "model": _row_value(device, "model", ""),
            "firmware": _row_value(device, "firmware", ""),
            "kind": _row_value(device, "kind", "unknown"),
            "provider": _row_value(device, "provider", "generic"),
            "identity_confidence": int(_row_value(device, "identity_confidence", 0) or 0),
            "status": _row_value(device, "status", "unknown"),
        },
        "discovery": {
            "open_ports": sorted({int(p) for p in open_ports if str(p).isdigit()}),
            "evidence": [str(item) for item in evidence][:64],
            "onvif_present": bool(_row_value(device, "onvif_url", "")),
            "web_present": bool(_row_value(device, "web_url", "")),
            "rtsp_present": bool(_row_value(device, "rtsp_url", "")) or bool(channel_rows),
            "akdb_profile": metadata.get("akdb_profile", ""),
            "protocol_family": metadata.get("protocol_family", ""),
            "akdb_validation": metadata.get("akdb_validation", ""),
        },
        "channels": channel_rows,
        "summary": {
            "channels_saved": len(channel_rows),
            "channels_available": sum(1 for row in channel_rows if row["available"]),
            "main_profiles": sum(1 for row in channel_rows if row["main_rtsp"]),
            "sub_profiles": sum(1 for row in channel_rows if row["sub_rtsp"]),
            "audio_tracks": sum(1 for row in channel_rows if row.get("audio_codec")),
            "bidirectional_audio": sum(1 for row in channel_rows if row.get("audio_mode") == "bidirectional"),
        },
    }
    if akdb_profiles is not None:
        report["akdb_snapshot"] = akdb_profiles
    return report


def default_filename(device) -> str:
    maker = (_row_value(device, "manufacturer", "") or "unknown").strip().lower().replace(" ", "-")
    model = (_row_value(device, "model", "") or _row_value(device, "name", "") or "device").strip().lower()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in model)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return f"sentinel-compat-{maker}-{safe.strip('-') or 'device'}.json"


def write_report(path: str | Path, report: dict) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def build_discovery_homologation_report(device, *, sentinel_version: str) -> dict:
    """Build a small AKDB candidate directly from a discovery result.

    It intentionally excludes unit identifiers (IP/MAC/serial/UUID) from the
    portable report while preserving technical evidence useful for matching and
    later homologation.
    """
    from artin_akdb import build_field_report
    from .fingerprint import identify_device, evidence_for_device

    decision = identify_device(device)
    metadata = dict(getattr(device, "metadata", {}) or {})
    portable_evidence = evidence_for_device(device)
    # The matcher evidence text can include discovery details but never unit
    # addressing/credentials; URLs are represented only as presence booleans.
    portable_evidence.update({
        "open_ports": [int(p) for p in (metadata.get("open_ports") or []) if str(p).isdigit()],
        "observations": [str(x) for x in (metadata.get("evidence") or [])][:64],
        "onvif_present": bool(getattr(device, "onvif_url", "")),
        "web_present": bool(getattr(device, "web_url", "")),
        "rtsp_present": bool(getattr(device, "rtsp_url", "")),
    })
    # Remove the transient uuid-present marker; it is useful only locally and
    # contributes nothing to a product-level homologation profile.
    portable_evidence["identifiers"] = [
        value for value in (portable_evidence.get("identifiers") or []) if value != "uuid-present"
    ]
    identity = decision.to_dict()
    identity["observed_manufacturer"] = getattr(device, "manufacturer", "") or ""
    identity["observed_model"] = getattr(device, "model", "") or ""
    identity["observed_kind"] = str(getattr(device, "kind", "unknown") or "unknown")
    return build_field_report(
        source_app="artin-sentinel",
        source_version=sentinel_version,
        identity=identity,
        evidence=portable_evidence,
        domain_data={
            "domain": "sentinel",
            "provider": getattr(device, "provider", "generic") or "generic",
            "discovery_sources": list(metadata.get("discovery_sources") or []),
            "candidate_reason": "unknown-device" if not decision.stable_id else "profile-not-homologated",
        },
        privacy={
            "credentials_included": False,
            "ip_redacted": True,
            "mac_redacted": True,
            "serial_redacted": True,
            "uuid_redacted": True,
            "images_included": False,
            "audio_included": False,
        },
    )


def discovery_report_filename(device) -> str:
    manufacturer = (getattr(device, "manufacturer", "") or "unknown").strip().lower().replace(" ", "-")
    model = (getattr(device, "model", "") or getattr(device, "name", "") or "device").strip().lower()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in model)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return f"akdb-field-{manufacturer}-{safe.strip('-') or 'device'}.json"

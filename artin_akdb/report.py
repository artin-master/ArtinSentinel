from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

FIELD_REPORT_SCHEMA = "artin-akdb-field-report-v1"


def build_field_report(*, source_app: str, source_version: str, identity: Mapping[str, Any],
                       evidence: Mapping[str, Any], domain_data: Mapping[str, Any] | None = None,
                       privacy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Create one sanitized, reviewable AKDB homologation candidate.

    This is a transport format only. Creating the report never promotes a
    candidate to homologated knowledge.
    """
    return {
        "schema": FIELD_REPORT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"app": str(source_app), "version": str(source_version)},
        "review_state": "candidate",
        "identity": dict(identity),
        "evidence": dict(evidence),
        "domain_data": dict(domain_data or {}),
        "privacy": dict(privacy or {
            "credentials_included": False,
            "ip_redacted": True,
            "mac_redacted": True,
            "serial_redacted": True,
        }),
    }


def write_field_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    if report.get("schema") != FIELD_REPORT_SCHEMA:
        raise ValueError("invalid AKDB field report schema")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out

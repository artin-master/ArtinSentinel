"""Artin Knowledge Database shared core.

This package is intentionally application-neutral.  Sentinel, NetLens and
RescNow can share stable identities/evidence while keeping domain-specific
extensions separate.
"""

from .models import (
    CORE_VERSION, CORE_REVISION, SCHEMA_VERSION, DomainExtension, KnowledgeRecord,
    EVIDENCE_LAYERS, VALIDATION_STATES, HOMOLOGATION_STATES,
)
from .catalog import CORE_RECORDS, public_catalog, record_by_id, record_by_legacy_key
from .store import SharedAkdbStore, default_store_path
from .matcher import MatchResult, match_knowledge, best_knowledge_match
from .report import FIELD_REPORT_SCHEMA, build_field_report, write_field_report
from .exchange import APPLICATION_DOMAINS, BUNDLE_SCHEMA, build_bundle, validate_bundle, bundle_fingerprint, write_bundle
from .sync import AKDB_MANIFEST_SCHEMA, validate_manifest, bundle_delta, bundle_change_preview, knowledge_record_from_dict, domain_extension_from_dict

__all__ = [
    "CORE_VERSION", "CORE_REVISION", "SCHEMA_VERSION", "DomainExtension", "KnowledgeRecord",
    "EVIDENCE_LAYERS", "VALIDATION_STATES", "HOMOLOGATION_STATES", "CORE_RECORDS", "public_catalog",
    "record_by_id", "record_by_legacy_key", "SharedAkdbStore", "default_store_path",
    "APPLICATION_DOMAINS", "BUNDLE_SCHEMA", "build_bundle", "validate_bundle", "bundle_fingerprint", "write_bundle",
    "MatchResult", "match_knowledge", "best_knowledge_match",
    "FIELD_REPORT_SCHEMA", "build_field_report", "write_field_report",
    "AKDB_MANIFEST_SCHEMA", "validate_manifest", "bundle_delta", "bundle_change_preview", "knowledge_record_from_dict", "domain_extension_from_dict",
]

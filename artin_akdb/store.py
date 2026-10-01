from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .catalog import CORE_RECORDS
from .models import CORE_VERSION, CORE_REVISION, SCHEMA_VERSION, DomainExtension, KnowledgeRecord, EVIDENCE_LAYERS


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_store_path() -> Path:
    override = os.environ.get("ARTIN_AKDB_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "artin" / "akdb" / "akdb.sqlite3"


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class SharedAkdbStore:
    """Shared local AKDB for Artin applications.

    Official catalog knowledge, domain extensions, field evidence and local
    overrides are stored in separate layers.  The sync metadata lets every app
    answer two independent questions: "is official knowledge newer?" and
    "do I have local candidates not yet uploaded?".
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        parts: list[int] = []
        for piece in str(value or "0").split("."):
            try:
                parts.append(int(piece))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    def _meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row["value"] if row else default)

    def _set_meta(self, key: str, value: Any) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (str(key), str(value)))

    def _ensure_schema(self) -> None:
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        schema_row = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if schema_row and int(schema_row["value"] or 0) > SCHEMA_VERSION:
            raise RuntimeError(
                f"AKDB compartilhada usa schema {schema_row['value']}, mais novo que o suportado ({SCHEMA_VERSION}). "
                "Atualize este aplicativo Artin antes de gravar na base."
            )
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records(
                stable_id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                core_version TEXT NOT NULL,
                revision INTEGER NOT NULL,
                manufacturer TEXT NOT NULL,
                family TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                variant TEXT NOT NULL DEFAULT '',
                canonical_type TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                provenance_json TEXT NOT NULL DEFAULT '[]',
                domains_json TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS domain_extensions(
                stable_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                extension_schema TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(stable_id, domain)
            );
            CREATE TABLE IF NOT EXISTS domain_meta(
                domain TEXT PRIMARY KEY,
                extension_revision INTEGER NOT NULL DEFAULT 0,
                extension_schema TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_id TEXT NOT NULL DEFAULT '',
                app_id TEXT NOT NULL,
                evidence_layer TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence INTEGER NOT NULL DEFAULT 0,
                source_version TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS field_reports(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_id TEXT NOT NULL DEFAULT '',
                app_id TEXT NOT NULL,
                report_schema TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'candidate',
                content_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conflicts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                existing_revision INTEGER NOT NULL,
                incoming_revision INTEGER NOT NULL,
                detail TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submission_queue(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL UNIQUE,
                generation INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                remote_ref TEXT NOT NULL DEFAULT '',
                queued_at TEXT NOT NULL,
                submitted_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_akdb_evidence_record ON evidence(stable_id, app_id, observed_at);
            CREATE INDEX IF NOT EXISTS idx_akdb_report_record ON field_reports(stable_id, app_id, created_at);
            """
        )
        self.conn.execute(
            """INSERT OR IGNORE INTO submission_queue(report_id,generation,state,queued_at)
               SELECT id,0,'pending',created_at FROM field_reports"""
        )
        self._set_meta("schema_version", SCHEMA_VERSION)
        core_row = self._meta("core_version", "0")
        if self._version_tuple(CORE_VERSION) > self._version_tuple(core_row):
            self._set_meta("core_version", CORE_VERSION)
        for key, value in (
            ("core_revision", 0),
            ("last_official_revision", 0),
            ("local_generation", 0),
            ("last_uploaded_generation", 0),
            ("last_sync_at", ""),
            ("last_official_check_at", ""),
            ("official_release_revision", 0),
            ("official_bundle_sha256", ""),
        ):
            if self.conn.execute("SELECT 1 FROM meta WHERE key=?", (key,)).fetchone() is None:
                self._set_meta(key, value)
        self.conn.commit()

    def _bump_local_generation(self) -> int:
        value = int(self._meta("local_generation", "0") or 0) + 1
        self._set_meta("local_generation", value)
        return value

    def sync_catalog(
        self, records: Iterable[KnowledgeRecord] = CORE_RECORDS, *,
        core_version: str | None = None, core_revision: int | None = None,
        commit: bool = True,
    ) -> int:
        changed = 0
        now = utcnow()
        target_core_version = str(core_version or CORE_VERSION)
        target_core_revision = int(CORE_REVISION if core_revision is None else core_revision)
        for record in records:
            payload = record.to_dict()
            payload["core_version"] = target_core_version
            payload["core_revision"] = target_core_revision
            digest = _payload_hash(payload)
            existing = self.conn.execute(
                "SELECT content_hash,revision,payload_json FROM records WHERE stable_id=?", (record.stable_id,)
            ).fetchone()
            if existing:
                existing_revision = int(existing["revision"] or 0)
                if existing_revision > int(record.revision):
                    continue
                if existing_revision == int(record.revision):
                    if existing["content_hash"] == digest:
                        continue
                    # A new catalog release stamps a higher global revision
                    # into every record. This metadata-only change is safe to
                    # carry forward without claiming its identity changed.
                    try:
                        old_payload = json.loads(existing["payload_json"] or "{}")
                    except (ValueError, TypeError):
                        old_payload = {}
                    old_comparable = dict(old_payload) if isinstance(old_payload, dict) else {}
                    old_comparable.pop("core_revision", None)
                    new_comparable = json.loads(json.dumps({k: v for k, v in payload.items() if k != "core_revision"}))
                    if old_comparable == new_comparable:
                        self.conn.execute(
                            "UPDATE records SET payload_json=?,content_hash=?,updated_at=? WHERE stable_id=?",
                            (json.dumps(payload, ensure_ascii=False, sort_keys=True), digest, now, record.stable_id),
                        )
                        changed += 1
                        continue
                    self.conn.execute(
                        "INSERT INTO conflicts(stable_id,scope,existing_revision,incoming_revision,detail,observed_at) VALUES(?,?,?,?,?,?)",
                        (record.stable_id, "core", existing_revision, int(record.revision),
                         "same revision with different content; existing record preserved", now),
                    )
                    continue
            self.conn.execute(
                """INSERT INTO records(
                    stable_id,schema_version,core_version,revision,manufacturer,family,model,variant,
                    canonical_type,validation_status,provenance_json,domains_json,payload_json,content_hash,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(stable_id) DO UPDATE SET
                    schema_version=excluded.schema_version,core_version=excluded.core_version,revision=excluded.revision,
                    manufacturer=excluded.manufacturer,family=excluded.family,model=excluded.model,variant=excluded.variant,
                    canonical_type=excluded.canonical_type,validation_status=excluded.validation_status,
                    provenance_json=excluded.provenance_json,domains_json=excluded.domains_json,
                    payload_json=excluded.payload_json,content_hash=excluded.content_hash,updated_at=excluded.updated_at
                """,
                (
                    record.stable_id, SCHEMA_VERSION, target_core_version, record.revision, record.manufacturer,
                    record.family, record.model, record.variant, record.canonical_type, record.validation_status,
                    json.dumps(record.provenance, ensure_ascii=False), json.dumps(record.domains, ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True), digest, now,
                ),
            )
            changed += 1
        # A packaged catalog revision describes official knowledge; it does not
        # create a local/uploadable generation.
        if target_core_revision >= int(self._meta("core_revision", "0") or 0):
            self._set_meta("core_revision", target_core_revision)
            self._set_meta("core_version", target_core_version)
            self._set_meta("last_official_revision", max(target_core_revision, int(self._meta("last_official_revision", "0") or 0)))
        if commit:
            self.conn.commit()
        return changed

    def sync_extension(self, extension: DomainExtension, *, commit: bool = True) -> None:
        if not self.conn.execute("SELECT 1 FROM records WHERE stable_id=?", (extension.stable_id,)).fetchone():
            raise ValueError(f"AKDB extension references unknown stable_id: {extension.stable_id}")
        existing = self.conn.execute(
            "SELECT revision,payload_json FROM domain_extensions WHERE stable_id=? AND domain=?",
            (extension.stable_id, extension.domain),
        ).fetchone()
        payload_json = json.dumps(dict(extension.payload), ensure_ascii=False, sort_keys=True)
        if existing:
            existing_revision = int(existing["revision"] or 0)
            if existing_revision > int(extension.revision):
                return
            if existing_revision == int(extension.revision):
                if existing["payload_json"] == payload_json:
                    self._update_domain_meta(extension)
                    return
                self.conn.execute(
                    "INSERT INTO conflicts(stable_id,scope,existing_revision,incoming_revision,detail,observed_at) VALUES(?,?,?,?,?,?)",
                    (extension.stable_id, f"domain:{extension.domain}", existing_revision, int(extension.revision),
                     "same extension revision with different content; existing extension preserved", utcnow()),
                )
                if commit:
                    self.conn.commit()
                return
        self.conn.execute(
            """INSERT INTO domain_extensions(stable_id,domain,extension_schema,revision,payload_json,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(stable_id,domain) DO UPDATE SET extension_schema=excluded.extension_schema,
                   revision=excluded.revision,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
            (
                extension.stable_id, extension.domain, extension.extension_schema, int(extension.revision),
                payload_json, utcnow(),
            ),
        )
        self._update_domain_meta(extension)
        if commit:
            self.conn.commit()

    def _update_domain_meta(self, extension: DomainExtension) -> None:
        row = self.conn.execute("SELECT extension_revision FROM domain_meta WHERE domain=?", (extension.domain,)).fetchone()
        old = int(row["extension_revision"] or 0) if row else 0
        if int(extension.revision) >= old:
            self.conn.execute(
                """INSERT INTO domain_meta(domain,extension_revision,extension_schema,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(domain) DO UPDATE SET extension_revision=max(domain_meta.extension_revision,excluded.extension_revision),
                   extension_schema=excluded.extension_schema,updated_at=excluded.updated_at""",
                (extension.domain, int(extension.revision), extension.extension_schema, utcnow()),
            )

    def conflict_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) n FROM conflicts").fetchone()
        return int(row["n"] if row else 0)

    def record_evidence(
        self, *, app_id: str, evidence_layer: str, status: str, payload: dict[str, Any],
        stable_id: str = "", confidence: int = 0, source_version: str = "",
    ) -> int:
        if evidence_layer not in EVIDENCE_LAYERS:
            raise ValueError(f"invalid AKDB evidence layer: {evidence_layer}")
        cur = self.conn.execute(
            """INSERT INTO evidence(stable_id,app_id,evidence_layer,status,confidence,source_version,payload_json,observed_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                stable_id or "", str(app_id), evidence_layer, str(status), max(0, min(100, int(confidence))),
                str(source_version or ""), json.dumps(payload, ensure_ascii=False, sort_keys=True), utcnow(),
            ),
        )
        self._bump_local_generation()
        self.conn.commit()
        return int(cur.lastrowid)

    def register_field_report(self, *, app_id: str, report: dict[str, Any], stable_id: str = "") -> int:
        raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        existing = self.conn.execute("SELECT id FROM field_reports WHERE content_hash=?", (digest,)).fetchone()
        if existing:
            return int(existing["id"])
        cur = self.conn.execute(
            """INSERT INTO field_reports(stable_id,app_id,report_schema,status,content_hash,payload_json,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (stable_id or "", str(app_id), str(report.get("schema") or "unknown"),
             str(report.get("review_state") or "candidate"), digest,
             json.dumps(report, ensure_ascii=False, sort_keys=True), utcnow()),
        )
        generation = self._bump_local_generation()
        report_id = int(cur.lastrowid)
        self.conn.execute(
            """INSERT OR IGNORE INTO submission_queue(report_id,generation,state,queued_at) VALUES(?,?,'pending',?)""",
            (report_id, generation, utcnow()),
        )
        self.conn.commit()
        return report_id

    def pending_submission_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) n FROM submission_queue WHERE state IN ('pending','error')").fetchone()
        return int(row["n"] if row else 0)

    def pending_submissions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT q.id queue_id,q.report_id,q.generation,q.state,q.attempts,q.last_error,
                      r.app_id,r.content_hash,r.payload_json,r.created_at
               FROM submission_queue q JOIN field_reports r ON r.id=q.report_id
               WHERE q.state IN ('pending','error') ORDER BY q.id LIMIT ?""",
            (max(1, int(limit)),),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["report"] = json.loads(str(item.pop("payload_json")))
            except Exception:
                item["report"] = {}
            result.append(item)
        return result

    def mark_submission_result(self, queue_id: int, *, remote_ref: str = "", error: str = "") -> None:
        if error:
            self.conn.execute(
                "UPDATE submission_queue SET state='error',attempts=attempts+1,last_error=? WHERE id=?",
                (str(error)[:2000], int(queue_id)),
            )
        else:
            row = self.conn.execute("SELECT generation FROM submission_queue WHERE id=?", (int(queue_id),)).fetchone()
            self.conn.execute(
                "UPDATE submission_queue SET state='submitted',attempts=attempts+1,last_error='',remote_ref=?,submitted_at=? WHERE id=?",
                (str(remote_ref), utcnow(), int(queue_id)),
            )
            if row:
                uploaded = max(int(self._meta("last_uploaded_generation", "0") or 0), int(row["generation"] or 0))
                self._set_meta("last_uploaded_generation", uploaded)
                self._set_meta("last_sync_at", utcnow())
        self.conn.commit()

    def official_release_state(self) -> dict[str, Any]:
        return {
            "release_revision": int(self._meta("official_release_revision", "0") or 0),
            "bundle_sha256": self._meta("official_bundle_sha256", ""),
            "core_revision": int(self._meta("core_revision", "0") or 0),
            "core_version": self._meta("core_version", CORE_VERSION),
        }

    def mark_official_release(self, release_revision: int, bundle_sha256: str = "") -> None:
        self._set_meta("official_release_revision", max(int(release_revision), int(self._meta("official_release_revision", "0") or 0)))
        if bundle_sha256:
            self._set_meta("official_bundle_sha256", str(bundle_sha256))
        self._set_meta("last_official_check_at", utcnow())
        self.conn.commit()

    def apply_official_bundle(self, bundle: dict[str, Any], *, release_revision: int, bundle_sha256: str = "") -> dict[str, Any]:
        from .exchange import validate_bundle
        from .sync import knowledge_record_from_dict, domain_extension_from_dict
        from .sync import bundle_delta
        errors = validate_bundle(bundle)
        if errors:
            raise ValueError("invalid AKDB bundle: " + "; ".join(errors))
        records = [knowledge_record_from_dict(item) for item in (bundle.get("records") or [])]
        extensions = [domain_extension_from_dict(item) for item in (bundle.get("extensions") or [])]
        if self.conn.in_transaction:
            self.conn.commit()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = int(self._meta("official_release_revision", "0") or 0)
            if int(release_revision) < current:
                raise ValueError("AKDB release is older than the installed official release")
            if int(release_revision) == current and bundle_sha256 != self._meta("official_bundle_sha256", ""):
                raise ValueError("AKDB release revision already exists with different content")
            delta = bundle_delta(self, bundle)
            if delta["conflicts"] or delta["extension_conflicts"]:
                raise ValueError("AKDB has same-revision conflicts; review local knowledge before applying")
            changed = self.sync_catalog(
                records, core_version=str(bundle.get("core_version") or CORE_VERSION),
                core_revision=int(bundle.get("core_revision") or 0), commit=False,
            )
            ext_changed = 0
            for extension in extensions:
                before = self.conn.execute(
                    "SELECT revision,payload_json FROM domain_extensions WHERE stable_id=? AND domain=?",
                    (extension.stable_id, extension.domain),
                ).fetchone()
                self.sync_extension(extension, commit=False)
                after = self.conn.execute(
                    "SELECT revision,payload_json FROM domain_extensions WHERE stable_id=? AND domain=?",
                    (extension.stable_id, extension.domain),
                ).fetchone()
                if (before is None and after is not None) or (before and after and tuple(before) != tuple(after)):
                    ext_changed += 1
            self._set_meta("official_release_revision", int(release_revision))
            if bundle_sha256:
                self._set_meta("official_bundle_sha256", str(bundle_sha256))
            self._set_meta("last_official_check_at", utcnow())
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {"records_changed": changed, "extensions_changed": ext_changed, **self.official_release_state()}

    def evidence_count(self, *, app_id: str | None = None) -> int:
        if app_id:
            row = self.conn.execute("SELECT COUNT(*) n FROM evidence WHERE app_id=?", (app_id,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) n FROM evidence").fetchone()
        return int(row["n"] if row else 0)

    def field_report_count(self, *, app_id: str | None = None) -> int:
        if app_id:
            row = self.conn.execute("SELECT COUNT(*) n FROM field_reports WHERE app_id=?", (app_id,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) n FROM field_reports").fetchone()
        return int(row["n"] if row else 0)

    def record_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) n FROM records").fetchone()
        return int(row["n"] if row else 0)

    def sync_state(self, *, domain: str = "") -> dict[str, Any]:
        local_generation = int(self._meta("local_generation", "0") or 0)
        last_uploaded = int(self._meta("last_uploaded_generation", "0") or 0)
        domain_revision = 0
        domain_schema = ""
        if domain:
            row = self.conn.execute(
                "SELECT extension_revision,extension_schema FROM domain_meta WHERE domain=?", (domain,)
            ).fetchone()
            if row:
                domain_revision = int(row["extension_revision"] or 0)
                domain_schema = str(row["extension_schema"] or "")
        return {
            "schema_version": int(self._meta("schema_version", str(SCHEMA_VERSION)) or SCHEMA_VERSION),
            "core_version": self._meta("core_version", CORE_VERSION),
            "core_revision": int(self._meta("core_revision", "0") or 0),
            "last_official_revision": int(self._meta("last_official_revision", "0") or 0),
            "domain": domain,
            "domain_revision": domain_revision,
            "domain_schema": domain_schema,
            "local_generation": local_generation,
            "last_uploaded_generation": last_uploaded,
            "upload_pending": self.pending_submission_count() > 0 or local_generation > last_uploaded,
            "last_sync_at": self._meta("last_sync_at", ""),
            "last_official_check_at": self._meta("last_official_check_at", ""),
            "conflicts": self.conflict_count(),
            "pending_submissions": self.pending_submission_count(),
            "official_release_revision": int(self._meta("official_release_revision", "0") or 0),
            "official_bundle_sha256": self._meta("official_bundle_sha256", ""),
        }

    def mark_uploaded(self, generation: int | None = None) -> None:
        current = int(self._meta("local_generation", "0") or 0)
        value = current if generation is None else min(current, max(0, int(generation)))
        self._set_meta("last_uploaded_generation", value)
        self._set_meta("last_sync_at", utcnow())
        self.conn.commit()

    def mark_official_check(self, remote_revision: int | None = None) -> None:
        self._set_meta("last_official_check_at", utcnow())
        if remote_revision is not None:
            current = int(self._meta("last_official_revision", "0") or 0)
            self._set_meta("last_official_revision", max(current, int(remote_revision)))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

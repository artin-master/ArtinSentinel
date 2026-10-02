from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path

from .domain import Device


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sites(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL UNIQUE,
 description TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS devices(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 site_id INTEGER,
 name TEXT NOT NULL,
 ip TEXT NOT NULL,
 port INTEGER,
 mac TEXT NOT NULL DEFAULT '',
 manufacturer TEXT NOT NULL DEFAULT '',
 model TEXT NOT NULL DEFAULT '',
 firmware TEXT NOT NULL DEFAULT '',
 serial TEXT NOT NULL DEFAULT '',
 uuid TEXT NOT NULL DEFAULT '',
 kind TEXT NOT NULL DEFAULT 'unknown',
 provider TEXT NOT NULL DEFAULT 'generic',
 status TEXT NOT NULL DEFAULT 'unknown',
 onvif_url TEXT NOT NULL DEFAULT '',
 rtsp_url TEXT NOT NULL DEFAULT '',
 web_url TEXT NOT NULL DEFAULT '',
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(site_id) REFERENCES sites(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_site_ip ON devices(site_id, ip);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 device_id INTEGER,
 site_id INTEGER,
 severity TEXT NOT NULL,
 event_type TEXT NOT NULL,
 message TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recorder_channels(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 device_id INTEGER NOT NULL,
 channel_no INTEGER NOT NULL,
 name TEXT NOT NULL DEFAULT '',
 rtsp_url TEXT NOT NULL DEFAULT '',
 available INTEGER NOT NULL DEFAULT 0,
 detail TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL,
 UNIQUE(device_id, channel_no),
 FOREIGN KEY(device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS live_workspaces(
 site_id INTEGER PRIMARY KEY,
 grid_count INTEGER NOT NULL DEFAULT 4,
 slots_json TEXT NOT NULL DEFAULT '[]',
 ask_stream INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(site_id) REFERENCES sites(id)
);
CREATE TABLE IF NOT EXISTS live_presets(
 site_id INTEGER NOT NULL,
 name TEXT NOT NULL COLLATE NOCASE,
 grid_count INTEGER NOT NULL,
 slots_json TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(site_id, name),
 FOREIGN KEY(site_id) REFERENCES sites(id)
);
CREATE TABLE IF NOT EXISTS live_windows(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 site_id INTEGER NOT NULL,
 window_key TEXT NOT NULL,
 title TEXT NOT NULL DEFAULT 'Monitoramento',
 screen_name TEXT NOT NULL DEFAULT '',
 geometry_json TEXT NOT NULL DEFAULT '{}',
 grid_count INTEGER NOT NULL DEFAULT 4,
 slots_json TEXT NOT NULL DEFAULT '[]',
 fullscreen INTEGER NOT NULL DEFAULT 0,
 enabled INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL,
 UNIQUE(site_id, window_key),
 FOREIGN KEY(site_id) REFERENCES sites(id)
);
CREATE TABLE IF NOT EXISTS observations(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 device_id INTEGER NOT NULL,
 status TEXT NOT NULL,
 latency_ms REAL,
 rtsp_ok INTEGER,
 http_ok INTEGER,
 created_at TEXT NOT NULL
);
"""


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def changed_channel_routes(before, after) -> set[int]:
    """Find persisted channels whose validated media route changed on rescan."""
    def route(row):
        return tuple(str(row[key] or "") for key in (
            "rtsp_url", "main_rtsp_url", "sub_rtsp_url", "route_kind"
        ))
    prior = {int(row["id"]): route(row) for row in before}
    return {int(row["id"]) for row in after
            if bool(row["available"]) and int(row["id"]) in prior
            and route(row) != prior[int(row["id"])]}


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate_017()
        self._migrate_0219()
        self._migrate_0220()
        self._migrate_0226()
        self._migrate_web_services()
        self.ensure_default_site()

    def _migrate_web_services(self):
        """Keep Web confirmation evidence separate from configured URL hints."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS device_web_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_id INTEGER NOT NULL,
                scheme TEXT NOT NULL CHECK (scheme IN ('http', 'https')),
                port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
                first_checked_at TEXT NOT NULL,
                last_checked_at TEXT NOT NULL,
                first_confirmed_at TEXT,
                last_confirmed_at TEXT,
                last_failed_at TEXT,
                last_outcome TEXT NOT NULL CHECK (last_outcome IN ('confirmed', 'failed')),
                last_http_status INTEGER CHECK (last_http_status BETWEEN 200 AND 599),
                last_tls_status TEXT NOT NULL
                    CHECK (last_tls_status IN ('not_applicable', 'verified', 'unverified')),
                last_error_code TEXT NOT NULL DEFAULT ''
                    CHECK (last_error_code IN ('', 'timeout', 'connection_error',
                                              'tls_error', 'invalid_response', 'other_error')),
                consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
                UNIQUE (endpoint_id, scheme, port),
                FOREIGN KEY (endpoint_id) REFERENCES device_endpoints(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS device_web_service_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL,
                checked_at TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN ('confirmed', 'failed')),
                http_status INTEGER CHECK (http_status BETWEEN 200 AND 599),
                tls_status TEXT NOT NULL
                    CHECK (tls_status IN ('not_applicable', 'verified', 'unverified')),
                error_code TEXT NOT NULL DEFAULT ''
                    CHECK (error_code IN ('', 'timeout', 'connection_error',
                                         'tls_error', 'invalid_response', 'other_error')),
                latency_ms REAL CHECK (latency_ms >= 0),
                FOREIGN KEY (service_id) REFERENCES device_web_services(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_web_service_checks_history
                ON device_web_service_checks(service_id, checked_at, id);
        """)

    def _column_names(self, table: str) -> set[str]:
        return {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}

    def _add_column(self, table: str, definition: str):
        name = definition.split()[0]
        if name not in self._column_names(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def _migrate_017(self):
        # Device operational identity and credential metadata. The password itself
        # never belongs to SQLite; it is handled by the OS keyring.
        self._add_column("devices", "detected_name TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "name_locked INTEGER NOT NULL DEFAULT 0")
        self._add_column("devices", "credential_username TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "credential_saved INTEGER NOT NULL DEFAULT 0")
        self._add_column("devices", "archived INTEGER NOT NULL DEFAULT 0")
        self._add_column("devices", "ignored_discovery INTEGER NOT NULL DEFAULT 0")
        self._add_column("devices", "identity_confidence INTEGER NOT NULL DEFAULT 0")
        # 0.2.7: keep operator overrides separate from automatically detected identity.
        self._add_column("devices", "identity_locked INTEGER NOT NULL DEFAULT 0")
        self._add_column("devices", "detected_manufacturer TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "detected_model TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "detected_kind TEXT NOT NULL DEFAULT 'unknown'")
        self._add_column("devices", "detected_provider TEXT NOT NULL DEFAULT 'generic'")
        # 0.2.14: persist operator identity separately from both effective and detected identity.
        self._add_column("devices", "manual_kind TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "manual_manufacturer TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "manual_model TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "manual_identity_updated_at TEXT NOT NULL DEFAULT ''")
        self._add_column("sites", "archived INTEGER NOT NULL DEFAULT 0")

        # Preserve provider/source channel names separately from operator aliases,
        # and keep both RTSP profiles available for the VMS workspace.
        self._add_column("recorder_channels", "source_name TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "alias TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "main_rtsp_url TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "sub_rtsp_url TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "preferred_stream TEXT NOT NULL DEFAULT 'auto'")
        self._add_column("recorder_channels", "last_good_stream TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "route_kind TEXT NOT NULL DEFAULT 'via_recorder'")
        self._add_column("recorder_channels", "channel_kind TEXT NOT NULL DEFAULT 'unknown'")
        self._add_column("recorder_channels", "audio_mode TEXT NOT NULL DEFAULT 'unknown'")
        self._add_column("recorder_channels", "audio_codec TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "audio_sample_rate INTEGER NOT NULL DEFAULT 0")
        self._add_column("recorder_channels", "audio_channels INTEGER NOT NULL DEFAULT 0")
        self._add_column("recorder_channels", "audio_detail TEXT NOT NULL DEFAULT ''")

        self.conn.execute(
            "UPDATE devices SET detected_name=name WHERE detected_name='' OR detected_name IS NULL"
        )
        self.conn.execute("UPDATE devices SET detected_manufacturer=manufacturer WHERE detected_manufacturer='' OR detected_manufacturer IS NULL")
        self.conn.execute("UPDATE devices SET detected_model=model WHERE detected_model='' OR detected_model IS NULL")
        self.conn.execute("UPDATE devices SET detected_kind=kind WHERE detected_kind='' OR detected_kind IS NULL")
        self.conn.execute("UPDATE devices SET detected_provider=provider WHERE detected_provider='' OR detected_provider IS NULL")
        # Migrate pre-0.2.14 identity locks into explicit manual fields.
        self.conn.execute("UPDATE devices SET manual_kind=kind WHERE identity_locked=1 AND (manual_kind='' OR manual_kind IS NULL)")
        self.conn.execute("UPDATE devices SET manual_manufacturer=manufacturer WHERE identity_locked=1 AND (manual_manufacturer='' OR manual_manufacturer IS NULL)")
        self.conn.execute("UPDATE devices SET manual_model=model WHERE identity_locked=1 AND (manual_model='' OR manual_model IS NULL)")
        # Preserve obvious friendly names created in older releases. Generic
        # discovery labels such as manufacturer/model/IP remain unlocked.
        for row in self.conn.execute("SELECT id,name,ip,manufacturer,model,name_locked FROM devices"):
            if row["name_locked"]:
                continue
            name = (row["name"] or "").strip()
            generic = {
                (row["ip"] or "").strip().casefold(),
                (row["manufacturer"] or "").strip().casefold(),
                (row["model"] or "").strip().casefold(),
                "intelbras", "hikvision", "dahua",
            }
            if name and name.casefold() not in generic:
                self.conn.execute("UPDATE devices SET name_locked=1 WHERE id=?", (row["id"],))
        self.conn.execute(
            "UPDATE recorder_channels SET source_name=name WHERE source_name='' OR source_name IS NULL"
        )
        self.conn.execute(
            "UPDATE recorder_channels SET main_rtsp_url=rtsp_url WHERE main_rtsp_url='' OR main_rtsp_url IS NULL"
        )
        self.conn.commit()


    def _migrate_0226(self):
        """0.2.26 — persistent operational health for recorder channels."""
        self._add_column("recorder_channels", "health_state TEXT NOT NULL DEFAULT 'unknown'")
        self._add_column("recorder_channels", "health_detail TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "source_ip TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "source_port INTEGER NOT NULL DEFAULT 0")
        self._add_column("recorder_channels", "source_protocol TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "health_fail_count INTEGER NOT NULL DEFAULT 0")
        self._add_column("recorder_channels", "health_last_checked_at TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "health_last_change_at TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "health_last_ok_at TEXT NOT NULL DEFAULT ''")
        self._add_column("recorder_channels", "health_last_problem_at TEXT NOT NULL DEFAULT ''")
        self.conn.commit()

    @staticmethod
    def _normalized_mac(mac: str) -> str:
        value = (mac or "").strip().lower().replace("-", ":")
        parts = [part.zfill(2) for part in value.split(":") if part]
        if len(parts) != 6:
            return ""
        return ":".join(parts)

    def _migrate_0219(self):
        """0.2.19 — physical-device identity may expose multiple IP endpoints.

        Existing device rows are preserved for auditability. Rows proven to share
        the same non-empty MAC inside the same Site are linked to one canonical
        record through ``correlated_to``; no row is deleted and no channel is
        rewritten. New discovery data is stored in ``device_endpoints``.
        """
        self._add_column("devices", "correlated_to INTEGER NOT NULL DEFAULT 0")
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS device_endpoints(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                ip TEXT NOT NULL,
                mac TEXT NOT NULL DEFAULT '',
                interface TEXT NOT NULL DEFAULT '',
                web_url TEXT NOT NULL DEFAULT '',
                rtsp_url TEXT NOT NULL DEFAULT '',
                onvif_url TEXT NOT NULL DEFAULT '',
                services_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'unknown',
                is_primary INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(device_id, ip),
                FOREIGN KEY(device_id) REFERENCES devices(id)
            )"""
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_endpoints_ip ON device_endpoints(ip)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_device_endpoints_mac ON device_endpoints(mac)"
        )

        # Seed an endpoint for every historical device before correlation.
        for row in self.conn.execute("SELECT * FROM devices ORDER BY id").fetchall():
            metadata = {}
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except Exception:
                metadata = {}
            services = metadata.get("open_ports") if isinstance(metadata, dict) else []
            interface = metadata.get("interface", "") if isinstance(metadata, dict) else ""
            self._upsert_endpoint_row(
                int(row["id"]), row["ip"], row["mac"], interface,
                row["web_url"], row["rtsp_url"], row["onvif_url"], services,
                row["status"], is_primary=True,
            )

        # Link pre-0.2.19 duplicates conservatively: same Site + exact MAC only.
        groups = self.conn.execute(
            """SELECT site_id, lower(mac) mac_key, COUNT(*) qty
               FROM devices
               WHERE trim(mac)<>'' AND correlated_to=0
               GROUP BY site_id, lower(mac)
               HAVING COUNT(*)>1"""
        ).fetchall()
        for group in groups:
            rows = self.conn.execute(
                "SELECT * FROM devices WHERE site_id IS ? AND lower(mac)=? AND correlated_to=0 ORDER BY id",
                (group["site_id"], group["mac_key"]),
            ).fetchall()
            if len(rows) < 2:
                continue
            canonical = max(rows, key=self._canonical_device_score)
            canonical_id = int(canonical["id"])
            for row in rows:
                rid = int(row["id"])
                if rid == canonical_id:
                    continue
                self.conn.execute(
                    "UPDATE devices SET correlated_to=?,updated_at=? WHERE id=?",
                    (canonical_id, utcnow(), rid),
                )
                for ep in self.conn.execute(
                    "SELECT * FROM device_endpoints WHERE device_id=?", (rid,)
                ).fetchall():
                    self._upsert_endpoint_row(
                        canonical_id, ep["ip"], ep["mac"], ep["interface"], ep["web_url"],
                        ep["rtsp_url"], ep["onvif_url"],
                        json.loads(ep["services_json"] or "[]"), ep["status"], is_primary=False,
                    )
        self.conn.commit()

    def _migrate_0220(self):
        """0.2.20 — AKDB-driven identity and homologation metadata.

        These fields are cached operational metadata. The shared AKDB remains
        the canonical knowledge source; device rows only remember which stable
        identity matched and the evidence/confidence used at the time.
        """
        self._add_column("devices", "akdb_stable_id TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "canonical_type TEXT NOT NULL DEFAULT 'unknown'")
        self._add_column("devices", "device_subtype TEXT NOT NULL DEFAULT ''")
        self._add_column("devices", "homologation_status TEXT NOT NULL DEFAULT 'unknown'")
        self._add_column("devices", "fingerprint_confidence INTEGER NOT NULL DEFAULT 0")
        self._add_column("devices", "fingerprint_json TEXT NOT NULL DEFAULT '{}'")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_akdb_stable_id ON devices(akdb_stable_id)")
        # Backfill from already stored, read-only evidence so an upgrade gains
        # AKDB intelligence immediately; a fresh network scan is not required.
        try:
            from .fingerprint import apply_device_fingerprint
            from .domain import Device, DeviceKind, DeviceStatus
            for row in self.conn.execute("SELECT * FROM devices WHERE correlated_to=0").fetchall():
                try:
                    metadata = json.loads(row["metadata_json"] or "{}")
                except Exception:
                    metadata = {}
                try:
                    kind = DeviceKind(str(row["detected_kind"] or row["kind"] or "unknown"))
                except Exception:
                    kind = DeviceKind.UNKNOWN
                try:
                    status = DeviceStatus(str(row["status"] or "unknown"))
                except Exception:
                    status = DeviceStatus.UNKNOWN
                device = Device(
                    site_id=row["site_id"], name=row["detected_name"] or row["name"], ip=row["ip"],
                    mac=row["mac"], manufacturer=row["detected_manufacturer"] or row["manufacturer"],
                    model=row["detected_model"] or row["model"], firmware=row["firmware"], serial=row["serial"],
                    uuid=row["uuid"], kind=kind, provider=row["detected_provider"] or row["provider"],
                    status=status, onvif_url=row["onvif_url"], rtsp_url=row["rtsp_url"], web_url=row["web_url"],
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
                decision = apply_device_fingerprint(device)
                if not decision.stable_id and not decision.candidate:
                    continue
                locked = bool(row["identity_locked"])
                effective_kind = row["kind"] if locked else str(device.kind)
                effective_manufacturer = row["manufacturer"] if locked else (device.manufacturer or row["manufacturer"])
                effective_model = row["model"] if locked else (device.model or row["model"])
                effective_provider = row["provider"] if locked else (device.provider or row["provider"])
                fp = {
                    "reasons": device.metadata.get("akdb_reasons") or [],
                    "preferred_strategies": device.metadata.get("preferred_strategies") or [],
                    "avoid_strategies": device.metadata.get("avoid_strategies") or [],
                    "negative_knowledge": device.metadata.get("negative_knowledge") or [],
                }
                self.conn.execute(
                    """UPDATE devices SET kind=?,manufacturer=?,model=?,provider=?,metadata_json=?,
                    akdb_stable_id=?,canonical_type=?,device_subtype=?,homologation_status=?,
                    fingerprint_confidence=?,fingerprint_json=?,identity_confidence=max(identity_confidence,?),updated_at=?
                    WHERE id=?""",
                    (effective_kind, effective_manufacturer, effective_model, effective_provider,
                     json.dumps(device.metadata, ensure_ascii=False), decision.stable_id, decision.canonical_type,
                     decision.subtype, decision.validation_status if decision.stable_id else "candidate",
                     int(decision.confidence), json.dumps(fp, ensure_ascii=False), int(decision.confidence),
                     utcnow(), int(row["id"])),
                )
        except Exception:
            # Schema migration must never make the application unstartable only
            # because optional matching/backfill encountered legacy oddities.
            pass
        self.conn.commit()

    def _canonical_device_score(self, row) -> tuple:
        """Choose the operational record without deleting any correlated row."""
        did = int(row["id"])
        available = self.conn.execute(
            "SELECT COUNT(*) c FROM recorder_channels WHERE device_id=? AND available=1", (did,)
        ).fetchone()["c"]
        total = self.conn.execute(
            "SELECT COUNT(*) c FROM recorder_channels WHERE device_id=?", (did,)
        ).fetchone()["c"]
        profile = 0
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
            profile = 1 if isinstance(metadata, dict) and metadata.get("akdb_profile") else 0
        except Exception:
            pass
        provider = 1 if (row["provider"] or "generic") != "generic" else 0
        identity = int(bool(row["identity_locked"])) + int(bool(row["name_locked"]))
        routes = sum(bool(row[name]) for name in ("rtsp_url", "onvif_url", "web_url"))
        # Lowest historical id wins a true tie, keeping existing workspace refs stable.
        return (int(available), int(total), identity, profile, provider, routes, -did)

    def _upsert_endpoint_row(
        self, device_id: int, ip: str, mac: str = "", interface: str = "",
        web_url: str = "", rtsp_url: str = "", onvif_url: str = "", services=None,
        status: str = "unknown", *, is_primary: bool = False,
    ):
        ip = (ip or "").strip()
        if not ip:
            return
        now = utcnow()
        mac = self._normalized_mac(mac) or (mac or "").strip().lower()
        services_json = json.dumps(sorted(set(services or [])), ensure_ascii=False)
        self.conn.execute(
            """INSERT INTO device_endpoints(
                device_id,ip,mac,interface,web_url,rtsp_url,onvif_url,services_json,status,
                is_primary,last_seen_at,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(device_id,ip) DO UPDATE SET
                mac=CASE WHEN excluded.mac<>'' THEN excluded.mac ELSE device_endpoints.mac END,
                interface=CASE WHEN excluded.interface<>'' THEN excluded.interface ELSE device_endpoints.interface END,
                web_url=CASE WHEN excluded.web_url<>'' THEN excluded.web_url ELSE device_endpoints.web_url END,
                rtsp_url=CASE WHEN excluded.rtsp_url<>'' THEN excluded.rtsp_url ELSE device_endpoints.rtsp_url END,
                onvif_url=CASE WHEN excluded.onvif_url<>'' THEN excluded.onvif_url ELSE device_endpoints.onvif_url END,
                services_json=CASE WHEN excluded.services_json<>'[]' THEN excluded.services_json ELSE device_endpoints.services_json END,
                status=excluded.status,is_primary=max(device_endpoints.is_primary,excluded.is_primary),
                last_seen_at=excluded.last_seen_at,updated_at=excluded.updated_at""",
            (
                int(device_id), ip, mac, interface or "", web_url or "", rtsp_url or "", onvif_url or "",
                services_json, status or "unknown", int(bool(is_primary)), now, now, now,
            ),
        )

    def list_device_endpoints(self, device_id: int):
        device_id = int(device_id)
        canonical = self.get_device(device_id)
        if canonical and int(canonical["correlated_to"] or 0):
            device_id = int(canonical["correlated_to"])
        return list(self.conn.execute(
            """SELECT * FROM device_endpoints WHERE device_id=?
               ORDER BY is_primary DESC, ip""", (device_id,)
        ))

    def get_device_endpoint(self, device_id: int, ip: str):
        """Locate an existing endpoint without creating or confirming one."""
        target = str(ip).strip().lower()
        for endpoint in self.list_device_endpoints(device_id):
            if str(endpoint["ip"]).strip().lower() == target:
                return endpoint
        return None

    def record_web_service_check(
        self, endpoint_id: int, *, ip: str, scheme: str, port: int,
        confirmed: bool, http_status: int | None = None,
        tls_status: str = "not_applicable", error_code: str = "",
        latency_ms: float | None = None, transient: bool = False,
    ) -> int:
        """Atomically record structured evidence, never a URL or response text.

        A failure keeps earlier confirmations. Only literal IP endpoints can be
        persisted; callers must mark temporary tunnel results as transient.
        Unknown error text is reduced to a fixed code before touching SQLite.
        """
        endpoint = self.conn.execute(
            "SELECT * FROM device_endpoints WHERE id=?", (endpoint_id,)
        ).fetchone()
        if endpoint is None:
            raise ValueError("Endpoint inexistente.")
        try:
            address = ip_address(ip)
            endpoint_address = ip_address(endpoint["ip"])
        except ValueError:
            raise ValueError("A confirmação persistida exige um IP literal.") from None
        if address != endpoint_address:
            raise ValueError("A tentativa não pertence ao IP do endpoint.")
        mapped = getattr(address, "ipv4_mapped", None)
        if transient or address.is_loopback or address.is_unspecified or (mapped and mapped.is_loopback):
            raise ValueError("Serviços de loopback ou endpoints transitórios não são persistidos.")
        owner = self.get_device(int(endpoint["device_id"]))
        if owner is None:
            raise ValueError("Equipamento do endpoint inexistente.")
        owners = [owner]
        if int(owner["correlated_to"] or 0):
            canonical = self.get_device(int(owner["correlated_to"]))
            if canonical is not None:
                owners.append(canonical)
        for device in owners:
            metadata = json.loads(device["metadata_json"] or "{}")
            if isinstance(metadata, dict) and metadata.get("connection_mode") == "site_connector":
                raise ValueError("Serviços de endpoints de túnel não são persistidos.")
        if scheme not in ("http", "https") or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Esquema ou porta Web inválidos.")
        if type(confirmed) is not bool:
            raise ValueError("O resultado da confirmação deve ser booleano.")
        if confirmed:
            if type(http_status) is not int or not 200 <= http_status <= 599:
                raise ValueError("A confirmação exige um status HTTP válido.")
        elif http_status is not None:
            raise ValueError("Uma resposta HTTP válida deve ser registrada como confirmação.")
        allowed_tls = ("not_applicable",) if scheme == "http" else ("verified", "unverified")
        if tls_status not in allowed_tls:
            raise ValueError("Estado TLS incompatível com o esquema.")
        if latency_ms is not None and (
            type(latency_ms) not in (int, float) or not math.isfinite(latency_ms) or latency_ms < 0
        ):
            raise ValueError("Latência inválida.")
        allowed_errors = {"timeout", "connection_error", "tls_error", "invalid_response", "other_error"}
        safe_error = ""
        if not confirmed:
            safe_error = error_code if isinstance(error_code, str) and error_code in allowed_errors else "other_error"
        checked_at = utcnow()
        outcome = "confirmed" if confirmed else "failed"
        with self.conn:
            self.conn.execute("""
                INSERT INTO device_web_services (
                    endpoint_id,scheme,port,first_checked_at,last_checked_at,
                    first_confirmed_at,last_confirmed_at,last_failed_at,last_outcome,
                    last_http_status,last_tls_status,last_error_code,consecutive_failures
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(endpoint_id,scheme,port) DO UPDATE SET
                    last_checked_at=excluded.last_checked_at,
                    first_confirmed_at=COALESCE(device_web_services.first_confirmed_at,
                                                excluded.first_confirmed_at),
                    last_confirmed_at=COALESCE(excluded.last_confirmed_at,
                                               device_web_services.last_confirmed_at),
                    last_failed_at=COALESCE(excluded.last_failed_at,device_web_services.last_failed_at),
                    last_outcome=excluded.last_outcome,
                    last_http_status=excluded.last_http_status,
                    last_tls_status=excluded.last_tls_status,
                    last_error_code=excluded.last_error_code,
                    consecutive_failures=CASE WHEN excluded.last_outcome='confirmed' THEN 0
                                              ELSE device_web_services.consecutive_failures+1 END
            """, (
                endpoint_id, scheme, port, checked_at, checked_at,
                checked_at if confirmed else None, checked_at if confirmed else None,
                None if confirmed else checked_at, outcome, http_status, tls_status,
                safe_error, 0 if confirmed else 1,
            ))
            service_id = int(self.conn.execute(
                "SELECT id FROM device_web_services WHERE endpoint_id=? AND scheme=? AND port=?",
                (endpoint_id, scheme, port),
            ).fetchone()["id"])
            self.conn.execute("""
                INSERT INTO device_web_service_checks (
                    service_id,checked_at,outcome,http_status,tls_status,error_code,latency_ms
                ) VALUES (?,?,?,?,?,?,?)
            """, (service_id, checked_at, outcome, http_status, tls_status, safe_error, latency_ms))
        return service_id

    def list_device_web_services(self, device_id: int, confirmed_only: bool = True):
        device = self.get_device(int(device_id))
        if device is None:
            return []
        group_ids = self.correlated_device_ids(int(device_id))
        placeholders = ",".join("?" for _ in group_ids)
        confirmation_filter = "AND s.last_confirmed_at IS NOT NULL" if confirmed_only else ""
        return list(self.conn.execute(f"""
            SELECT s.*, e.ip AS endpoint_ip, e.is_primary
            FROM device_web_services s JOIN device_endpoints e ON e.id=s.endpoint_id
            WHERE e.device_id IN ({placeholders}) {confirmation_filter}
            ORDER BY e.is_primary DESC, e.ip, s.scheme, s.port
        """, group_ids))

    def list_web_service_checks(self, service_id: int, limit: int = 100):
        if type(limit) is not int or limit < 1:
            raise ValueError("O limite de histórico deve ser um inteiro positivo.")
        return list(self.conn.execute("""
            SELECT * FROM device_web_service_checks WHERE service_id=?
            ORDER BY checked_at DESC, id DESC LIMIT ?
        """, (service_id, limit)))

    def _delete_endpoint_web_services(self, endpoint_ids):
        if not endpoint_ids:
            return
        placeholders = ",".join("?" for _ in endpoint_ids)
        self.conn.execute(f"""
            DELETE FROM device_web_service_checks WHERE service_id IN (
                SELECT id FROM device_web_services WHERE endpoint_id IN ({placeholders})
            )
        """, endpoint_ids)
        self.conn.execute(
            f"DELETE FROM device_web_services WHERE endpoint_id IN ({placeholders})", endpoint_ids,
        )

    def correlated_device_ids(self, device_id: int) -> list[int]:
        device_id = int(device_id)
        row = self.get_device(device_id)
        if row and int(row["correlated_to"] or 0):
            device_id = int(row["correlated_to"])
        return [device_id] + [
            int(r["id"]) for r in self.conn.execute(
                "SELECT id FROM devices WHERE correlated_to=? ORDER BY id", (device_id,)
            )
        ]

    def find_canonical_by_site_mac(self, site_id: int, mac: str):
        norm = self._normalized_mac(mac)
        if not norm:
            return None
        rows = self.conn.execute(
            """SELECT * FROM devices WHERE site_id=? AND correlated_to=0
               AND lower(mac)=? ORDER BY id""", (int(site_id), norm)
        ).fetchall()
        if not rows:
            return None
        return max(rows, key=self._canonical_device_score)

    def register_device_endpoint(self, device_id: int, *, ip: str, mac: str = "", metadata=None,
                                 web_url: str = "", rtsp_url: str = "", onvif_url: str = "",
                                 status: str = "online", is_primary: bool = False):
        metadata = metadata or {}
        self._upsert_endpoint_row(
            int(device_id), ip, mac, str(metadata.get("interface") or ""), web_url, rtsp_url, onvif_url,
            metadata.get("open_ports") or [], status, is_primary=is_primary,
        )
        self.conn.commit()

    def update_endpoint_status(self, device_id: int, ip: str, status: str):
        row = self.get_device(int(device_id))
        if row and int(row["correlated_to"] or 0):
            device_id = int(row["correlated_to"])
        self.conn.execute(
            "UPDATE device_endpoints SET status=?,last_seen_at=?,updated_at=? WHERE device_id=? AND ip=?",
            (status, utcnow(), utcnow(), int(device_id), str(ip)),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def ensure_default_site(self):
        if not self.conn.execute("SELECT 1 FROM sites LIMIT 1").fetchone():
            self.add_site("Local", "Site padrão")

    def add_site(self, name: str, description: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO sites(name,description,created_at) VALUES(?,?,?)",
            (name.strip(), description.strip(), utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_sites(self, include_archived: bool = False):
        query = "SELECT * FROM sites"
        if not include_archived:
            query += " WHERE archived=0"
        query += " ORDER BY name COLLATE NOCASE"
        return list(self.conn.execute(query))

    def list_archived_sites(self):
        return list(self.conn.execute("SELECT * FROM sites WHERE archived=1 ORDER BY name COLLATE NOCASE"))

    def get_site(self, site_id: int):
        return self.conn.execute("SELECT * FROM sites WHERE id=?", (int(site_id),)).fetchone()

    def update_site(self, site_id: int, name: str, description: str = ""):
        name = name.strip()
        if not name:
            raise ValueError("O nome do Site não pode ficar vazio.")
        self.conn.execute(
            "UPDATE sites SET name=?,description=? WHERE id=?",
            (name, description.strip(), int(site_id)),
        )
        self.conn.commit()

    def archive_site(self, site_id: int, archived: bool = True):
        self.conn.execute(
            "UPDATE sites SET archived=? WHERE id=?",
            (int(bool(archived)), int(site_id)),
        )
        self.conn.commit()

    def delete_site_permanently(
        self,
        site_id: int,
        *,
        target_site_id: int | None = None,
        delete_devices: bool = False,
    ):
        site_id = int(site_id)
        site = self.get_site(site_id)
        if not site:
            raise ValueError("Site não encontrado.")
        devices = self.list_devices(site_id, include_archived=True)

        if devices and not delete_devices and target_site_id is None:
            raise ValueError("O Site possui equipamentos. Mova-os para outro Site ou confirme a exclusão conjunta.")

        if target_site_id is not None:
            target_site_id = int(target_site_id)
            if target_site_id == site_id:
                raise ValueError("Escolha outro Site como destino.")
            target = self.get_site(target_site_id)
            if not target or target["archived"]:
                raise ValueError("O Site de destino não está disponível.")
            # Preserve the unique (site, IP) rule rather than silently merging records.
            for device in devices:
                conflict = self.find_device_by_site_ip(target_site_id, device["ip"])
                if conflict and int(conflict["id"]) != int(device["id"]):
                    raise ValueError(
                        f"O Site de destino já possui um equipamento com o IP {device['ip']}. "
                        "Resolva a duplicidade antes de mover o Site."
                    )
            device_ids = [int(d["id"]) for d in devices]
            if device_ids:
                placeholders = ",".join("?" for _ in device_ids)
                self.conn.execute(
                    f"UPDATE devices SET site_id=?,updated_at=? WHERE id IN ({placeholders})",
                    (target_site_id, utcnow(), *device_ids),
                )
                self.conn.execute(
                    f"UPDATE events SET site_id=? WHERE device_id IN ({placeholders})",
                    (target_site_id, *device_ids),
                )
        elif delete_devices:
            for device in list(devices):
                self.delete_device_permanently(int(device["id"]))

        self.conn.execute("DELETE FROM live_workspaces WHERE site_id=?", (site_id,))
        self.conn.execute("DELETE FROM live_presets WHERE site_id=?", (site_id,))
        self.conn.execute("DELETE FROM events WHERE site_id=?", (site_id,))
        self.conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
        self.conn.commit()

    def upsert_device(self, d: Device) -> int:
        """Insert/update one physical device while preserving multiple IP endpoints.

        Starting in 0.2.19, a strong same-Site + same-MAC match is treated as the
        same physical device. The first/best record remains canonical; every IP
        is kept in ``device_endpoints``. Historical duplicate rows are linked via
        ``correlated_to`` instead of being deleted.
        """
        now = utcnow()
        row = self.conn.execute(
            "SELECT * FROM devices WHERE site_id IS ? AND ip=?", (d.site_id, d.ip)
        ).fetchone()
        norm_mac = self._normalized_mac(d.mac)
        peer = self.find_canonical_by_site_mac(int(d.site_id), norm_mac) if (d.site_id is not None and norm_mac) else None

        # If this exact-IP row was previously linked to another physical identity,
        # route all fresh evidence into the canonical record.
        if row and int(row["correlated_to"] or 0):
            canonical = self.get_device(int(row["correlated_to"]))
            if canonical:
                peer = canonical

        metadata_json = json.dumps(d.metadata, ensure_ascii=False)
        identity_confidence = int(d.metadata.get("identity_confidence", 0) or 0)

        # New IP for an already known MAC: do not create another physical device.
        if not row and peer is not None:
            canonical_id = int(peer["id"])
            self._merge_discovery_into_device(canonical_id, d, metadata_json, identity_confidence, now)
            self._upsert_endpoint_row(
                canonical_id, d.ip, norm_mac or d.mac,
                str(d.metadata.get("interface") or ""), d.web_url, d.rtsp_url, d.onvif_url,
                d.metadata.get("open_ports") or [], str(d.status), is_primary=False,
            )
            self.conn.commit()
            return canonical_id

        if row:
            target_id = int(peer["id"]) if peer is not None else int(row["id"])
            if target_id != int(row["id"]):
                self.conn.execute(
                    "UPDATE devices SET correlated_to=?,updated_at=? WHERE id=?",
                    (target_id, now, int(row["id"])),
                )
            self._merge_discovery_into_device(target_id, d, metadata_json, identity_confidence, now)
            self._upsert_endpoint_row(
                target_id, d.ip, norm_mac or d.mac,
                str(d.metadata.get("interface") or ""), d.web_url, d.rtsp_url, d.onvif_url,
                d.metadata.get("open_ports") or [], str(d.status),
                is_primary=(target_id == int(row["id"])),
            )
            self.conn.commit()
            return target_id

        cur = self.conn.execute(
            """INSERT INTO devices(
            site_id,name,detected_name,name_locked,ip,port,mac,manufacturer,model,firmware,serial,uuid,
            kind,provider,status,onvif_url,rtsp_url,web_url,metadata_json,identity_confidence,
            identity_locked,detected_manufacturer,detected_model,detected_kind,detected_provider,
            akdb_stable_id,canonical_type,device_subtype,homologation_status,fingerprint_confidence,fingerprint_json,
            created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                d.site_id, d.name, d.name, 0, d.ip, d.port, norm_mac or d.mac, d.manufacturer, d.model,
                d.firmware, d.serial, d.uuid, str(d.kind), d.provider, str(d.status), d.onvif_url,
                d.rtsp_url, d.web_url, metadata_json, identity_confidence, 0,
                d.manufacturer, d.model, str(d.kind), d.provider,
                str(d.metadata.get("akdb_stable_id") or ""), str(d.metadata.get("canonical_type") or "unknown"),
                str(d.metadata.get("device_subtype") or ""), str(d.metadata.get("homologation_status") or "unknown"),
                int(d.metadata.get("akdb_confidence") or identity_confidence or 0),
                json.dumps({"reasons": d.metadata.get("akdb_reasons") or [], "preferred_strategies": d.metadata.get("preferred_strategies") or [], "avoid_strategies": d.metadata.get("avoid_strategies") or []}, ensure_ascii=False),
                now, now,
            ),
        )
        device_id = int(cur.lastrowid)
        self._upsert_endpoint_row(
            device_id, d.ip, norm_mac or d.mac, str(d.metadata.get("interface") or ""),
            d.web_url, d.rtsp_url, d.onvif_url, d.metadata.get("open_ports") or [],
            str(d.status), is_primary=True,
        )
        self.conn.commit()
        return device_id

    def _merge_discovery_into_device(self, device_id: int, d: Device, metadata_json: str,
                                     identity_confidence: int, now: str):
        row = self.get_device(int(device_id))
        if not row:
            return
        def weak_identity(value: str, manufacturer: str = "") -> bool:
            folded = (value or "").strip().casefold()
            maker = (manufacturer or "").strip().casefold()
            if not folded:
                return True
            return (
                folded in {"web viewer", "ip camera", "câmera ip", "camera", "ipc", "equipamento", maker}
                or folded.startswith("possível cftv")
                or folded.startswith("onvif ")
            )

        identity_locked = bool(row["identity_locked"])
        current_model = str(row["model"] or "")
        incoming_model = str(d.model or "")
        if identity_locked:
            effective_model = current_model
        elif current_model and not weak_identity(current_model, row["manufacturer"]) and weak_identity(incoming_model, d.manufacturer):
            effective_model = current_model
        else:
            effective_model = incoming_model or current_model

        current_name = str(row["name"] or "")
        incoming_name = str(d.name or "")
        if row["name_locked"]:
            effective_name = current_name
        elif current_name and not weak_identity(current_name, row["manufacturer"]) and weak_identity(incoming_name, d.manufacturer):
            effective_name = current_name
        else:
            effective_name = incoming_name or current_name

        effective_manufacturer = row["manufacturer"] if identity_locked else (d.manufacturer or row["manufacturer"])
        effective_kind = row["kind"] if identity_locked else (str(d.kind) if str(d.kind) != "unknown" else row["kind"])
        detected_model = incoming_model
        if current_model and not weak_identity(current_model, row["manufacturer"]) and weak_identity(incoming_model, d.manufacturer):
            detected_model = row["detected_model"] or current_model
        provider = d.provider if d.provider and d.provider != "generic" else row["provider"]
        mac = self._normalized_mac(d.mac) or row["mac"] or d.mac
        try:
            stored_metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            stored_metadata = {}
        try:
            incoming_metadata = json.loads(metadata_json or "{}")
        except Exception:
            incoming_metadata = {}
        merged_metadata = dict(stored_metadata) if isinstance(stored_metadata, dict) else {}
        if isinstance(incoming_metadata, dict):
            for key, value in incoming_metadata.items():
                if key in {"evidence", "discovery_sources", "open_ports"}:
                    before = merged_metadata.get(key) or []
                    if isinstance(before, list) and isinstance(value, list):
                        merged_metadata[key] = list(dict.fromkeys(before + value))
                    elif value:
                        merged_metadata[key] = value
                elif value not in (None, "", [], {}):
                    merged_metadata[key] = value
        metadata_json = json.dumps(merged_metadata, ensure_ascii=False)
        akdb_stable_id = str(merged_metadata.get("akdb_stable_id") or row["akdb_stable_id"] or "")
        canonical_type = str(merged_metadata.get("canonical_type") or row["canonical_type"] or "unknown")
        device_subtype = str(merged_metadata.get("device_subtype") or row["device_subtype"] or "")
        homologation_status = str(merged_metadata.get("homologation_status") or row["homologation_status"] or "unknown")
        fingerprint_confidence = max(int(row["fingerprint_confidence"] or 0), int(merged_metadata.get("akdb_confidence") or 0))
        fingerprint_json = json.dumps({
            "reasons": merged_metadata.get("akdb_reasons") or [],
            "preferred_strategies": merged_metadata.get("preferred_strategies") or [],
            "avoid_strategies": merged_metadata.get("avoid_strategies") or [],
            "negative_knowledge": merged_metadata.get("negative_knowledge") or [],
        }, ensure_ascii=False)
        # Endpoint-specific routes stay in device_endpoints. The physical record
        # keeps the best known primary routes for compatibility with older code.
        self.conn.execute(
            """UPDATE devices SET
            name=?,detected_name=?,port=COALESCE(?,port),mac=?,manufacturer=?,model=?,firmware=?,
            serial=?,uuid=?,kind=?,provider=?,status=?,
            onvif_url=CASE WHEN onvif_url='' THEN ? ELSE onvif_url END,
            rtsp_url=CASE WHEN rtsp_url='' THEN ? ELSE rtsp_url END,
            web_url=CASE WHEN web_url='' THEN ? ELSE web_url END,
            metadata_json=?,identity_confidence=max(identity_confidence,?),
            detected_manufacturer=?,detected_model=?,detected_kind=?,detected_provider=?,
            akdb_stable_id=?,canonical_type=?,device_subtype=?,homologation_status=?,
            fingerprint_confidence=?,fingerprint_json=?,updated_at=? WHERE id=?""",
            (
                effective_name, d.name or row["detected_name"], d.port, mac,
                effective_manufacturer, effective_model, d.firmware or row["firmware"],
                d.serial or row["serial"], d.uuid or row["uuid"], effective_kind, provider,
                str(d.status), d.onvif_url, d.rtsp_url, d.web_url, metadata_json,
                identity_confidence, d.manufacturer or row["detected_manufacturer"],
                detected_model or row["detected_model"],
                str(d.kind) if str(d.kind) != "unknown" else row["detected_kind"],
                d.provider or row["detected_provider"], akdb_stable_id, canonical_type, device_subtype,
                homologation_status, fingerprint_confidence, fingerprint_json, now, int(device_id),
            ),
        )

    def list_devices(self, site_id=None, include_archived: bool = False):
        clauses = []
        args = []
        if site_id is not None:
            clauses.append("site_id=?")
            args.append(site_id)
        if not include_archived:
            clauses.append("archived=0")
        # 0.2.19: correlated secondary-IP rows remain in SQLite for audit/history
        # but are not separate physical devices in normal UI/monitoring lists.
        clauses.append("correlated_to=0")
        query = "SELECT * FROM devices"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY name COLLATE NOCASE, ip"
        return list(self.conn.execute(query, tuple(args)))

    def list_archived_devices(self, site_id=None):
        if site_id is None:
            return list(self.conn.execute("SELECT * FROM devices WHERE archived=1 AND correlated_to=0 ORDER BY name COLLATE NOCASE, ip"))
        return list(self.conn.execute("SELECT * FROM devices WHERE site_id=? AND archived=1 AND correlated_to=0 ORDER BY name COLLATE NOCASE, ip", (site_id,)))

    def get_device(self, device_id: int):
        return self.conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()

    def archive_device(self, device_id: int, archived: bool = True):
        ids = self.correlated_device_ids(int(device_id))
        placeholders = ",".join("?" for _ in ids)
        self.conn.execute(
            f"UPDATE devices SET archived=?,updated_at=? WHERE id IN ({placeholders})",
            (int(bool(archived)), utcnow(), *ids),
        )
        self.conn.commit()

    def set_ignore_discovery(self, device_id: int, ignored: bool = True):
        ids = self.correlated_device_ids(int(device_id))
        placeholders = ",".join("?" for _ in ids)
        self.conn.execute(
            f"UPDATE devices SET ignored_discovery=?,updated_at=? WHERE id IN ({placeholders})",
            (int(bool(ignored)), utcnow(), *ids),
        )
        self.conn.commit()

    def merge_device_metadata(self, device_id: int, patch: dict) -> dict:
        """Merge sanitized runtime capability evidence into one device record.

        Used by read-only provider probes. Callers must never place passwords,
        tokens or authorization headers in ``patch``.
        """
        row = self.get_device(int(device_id))
        if not row:
            return {}
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        for key, value in dict(patch or {}).items():
            metadata[str(key)] = value
        self.conn.execute(
            "UPDATE devices SET metadata_json=?,updated_at=? WHERE id=?",
            (json.dumps(metadata, ensure_ascii=False), utcnow(), int(device_id)),
        )
        self.conn.commit()
        return metadata

    def delete_device_permanently(self, device_id: int):
        device_id = int(device_id)
        group_ids = self.correlated_device_ids(device_id)
        canonical_id = group_ids[0]
        # Workspace slots reference channels/devices by id; remove only matching
        # physical-device references and preserve every unrelated slot.
        for ws in self.conn.execute("SELECT site_id,slots_json FROM live_workspaces").fetchall():
            try:
                slots = json.loads(ws["slots_json"] or "[]")
            except json.JSONDecodeError:
                slots = []
            changed = False
            for idx, slot in enumerate(slots):
                if isinstance(slot, dict) and int(slot.get("device_id", -1)) in group_ids:
                    slots[idx] = {}
                    changed = True
            if changed:
                self.conn.execute(
                    "UPDATE live_workspaces SET slots_json=?,updated_at=? WHERE site_id=?",
                    (json.dumps(slots, ensure_ascii=False), utcnow(), ws["site_id"]),
                )
        placeholders = ",".join("?" for _ in group_ids)
        self.conn.execute(f"DELETE FROM observations WHERE device_id IN ({placeholders})", group_ids)
        self.conn.execute(f"DELETE FROM recorder_channels WHERE device_id IN ({placeholders})", group_ids)
        self.conn.execute(f"DELETE FROM events WHERE device_id IN ({placeholders})", group_ids)
        endpoint_ids = [int(row["id"]) for row in self.conn.execute(
            f"SELECT id FROM device_endpoints WHERE device_id IN ({placeholders})", group_ids,
        )]
        self._delete_endpoint_web_services(endpoint_ids)
        self.conn.execute("DELETE FROM device_endpoints WHERE device_id=?", (canonical_id,))
        # Historical secondary rows may still own seed endpoint rows if an old
        # migration was interrupted; remove them too before deleting devices.
        if len(group_ids) > 1:
            self.conn.execute(f"DELETE FROM device_endpoints WHERE device_id IN ({placeholders})", group_ids)
        self.conn.execute(f"DELETE FROM devices WHERE id IN ({placeholders})", group_ids)
        self.conn.commit()

    def find_known_for_discovery(self, site_id: int, device) :
        """Return an existing physical identity using strong unit evidence only.

        A model/AKDB stable-id describes a product type, not a physical unit, so
        it is never sufficient for suppression. IP/endpoints, MAC, serial and
        UUID are unit-level evidence. Archived/ignored devices are still known.
        """
        site_id = int(site_id)
        ip = str(getattr(device, "ip", "") or "")
        if ip:
            row = self.conn.execute(
                "SELECT * FROM devices WHERE site_id=? AND ip=? ORDER BY correlated_to ASC,id LIMIT 1",
                (site_id, ip),
            ).fetchone()
            if row:
                if int(row["correlated_to"] or 0):
                    return self.get_device(int(row["correlated_to"])) or row
                return row
            ep = self.conn.execute(
                """SELECT d.* FROM device_endpoints e JOIN devices d ON d.id=e.device_id
                   WHERE d.site_id=? AND e.ip=? ORDER BY d.id LIMIT 1""", (site_id, ip)
            ).fetchone()
            if ep:
                return ep
        mac = self._normalized_mac(str(getattr(device, "mac", "") or ""))
        if mac:
            row = self.conn.execute(
                "SELECT * FROM devices WHERE site_id=? AND lower(mac)=? AND correlated_to=0 ORDER BY id LIMIT 1",
                (site_id, mac),
            ).fetchone()
            if row:
                return row
            row = self.conn.execute(
                """SELECT d.* FROM device_endpoints e JOIN devices d ON d.id=e.device_id
                   WHERE d.site_id=? AND lower(e.mac)=? ORDER BY d.id LIMIT 1""", (site_id, mac)
            ).fetchone()
            if row:
                return row
        for key in ("serial", "uuid"):
            value = str(getattr(device, key, "") or "").strip()
            if value:
                row = self.conn.execute(
                    f"SELECT * FROM devices WHERE site_id=? AND {key}=? AND correlated_to=0 ORDER BY id LIMIT 1",
                    (site_id, value),
                ).fetchone()
                if row:
                    return row
        return None

    def find_device_by_site_ip(self, site_id: int, ip: str):
        return self.conn.execute("SELECT * FROM devices WHERE site_id=? AND ip=?", (int(site_id), ip)).fetchone()

    def update_device_identity(self, device_id: int, name: str, kind: str, manufacturer: str, model: str):
        """Save an operator override without rewriting the detected fingerprint.

        ``manual_*`` is the authoritative operator layer. ``kind/manufacturer/model``
        remain the effective compatibility fields consumed by older code.
        """
        now = utcnow()
        kind = (kind or "unknown").strip()
        manufacturer = (manufacturer or "").strip()
        model = (model or "").strip()
        self.conn.execute(
            """UPDATE devices SET name=?,name_locked=1,identity_locked=1,
            kind=?,manufacturer=?,model=?,manual_kind=?,manual_manufacturer=?,manual_model=?,
            manual_identity_updated_at=?,updated_at=? WHERE id=?""",
            (name.strip(), kind, manufacturer, model, kind, manufacturer, model, now, now, int(device_id)),
        )
        self.conn.commit()

    def clear_device_identity_override(self, device_id: int):
        """Return routing identity to detected/AKDB control without losing evidence."""
        row = self.get_device(int(device_id))
        if not row:
            return
        now = utcnow()
        self.conn.execute(
            """UPDATE devices SET identity_locked=0,manual_kind='',manual_manufacturer='',manual_model='',
            manual_identity_updated_at='',manufacturer=?,model=?,kind=?,provider=?,updated_at=? WHERE id=?""",
            (row["detected_manufacturer"] or "", row["detected_model"] or "",
             row["detected_kind"] or "unknown", row["detected_provider"] or row["provider"] or "generic",
             now, int(device_id)),
        )
        self.conn.commit()

    def apply_detected_identity(
        self, device_id: int, *, manufacturer: str = "", model: str = "", kind: str = "",
        provider: str = "", firmware: str = "", serial: str = "", confidence: int | None = None,
    ):
        """Persist probe/ONVIF identity while respecting an operator override."""
        row = self.get_device(device_id)
        if not row:
            return
        detected_manufacturer = (manufacturer or row["detected_manufacturer"] or "").strip()
        detected_model = (model or row["detected_model"] or "").strip()
        detected_kind = (kind or row["detected_kind"] or "unknown").strip()
        detected_provider = (provider or row["detected_provider"] or row["provider"] or "generic").strip()
        locked = bool(row["identity_locked"])
        effective_manufacturer = row["manufacturer"] if locked else (manufacturer or row["manufacturer"])
        effective_model = row["model"] if locked else (model or row["model"])
        effective_kind = row["kind"] if locked else (kind or row["kind"])
        self.conn.execute(
            """UPDATE devices SET manufacturer=?,model=?,kind=?,provider=?,firmware=?,serial=?,
            detected_manufacturer=?,detected_model=?,detected_kind=?,detected_provider=?,
            identity_confidence=COALESCE(?,identity_confidence),updated_at=? WHERE id=?""",
            (effective_manufacturer, effective_model, effective_kind, detected_provider,
             firmware or row["firmware"], serial or row["serial"], detected_manufacturer,
             detected_model, detected_kind, detected_provider, confidence, utcnow(), int(device_id)),
        )
        self.conn.commit()

    def update_device_credential_meta(self, device_id: int, username: str, saved: bool):
        self.conn.execute(
            "UPDATE devices SET credential_username=?,credential_saved=?,updated_at=? WHERE id=?",
            (username.strip(), int(bool(saved)), utcnow(), int(device_id)),
        )
        self.conn.commit()

    def update_device_status(self, device_id: int, status: str):
        old = self.get_device(device_id)
        if not old:
            return
        if old["status"] != status:
            severity = "info" if status == "online" else "warning"
            event_type = "device_online" if status == "online" else "device_offline"
            message = f"{old['name']} ficou {status}."
            self.add_event(old["site_id"], device_id, severity, event_type, message)
        self.conn.execute(
            "UPDATE devices SET status=?,updated_at=? WHERE id=?", (status, utcnow(), device_id)
        )
        self.conn.commit()

    def add_event(self, site_id, device_id, severity, event_type, message):
        self.conn.execute(
            """INSERT INTO events(device_id,site_id,severity,event_type,message,created_at)
            VALUES(?,?,?,?,?,?)""",
            (device_id, site_id, severity, event_type, message, utcnow()),
        )
        self.conn.commit()

    def add_camera_event(self, device_id, event):
        """Reuse events with fixed, sanitized metadata and inventory-owned scope."""
        from .camera_events import CameraEvent, EVENT_TYPES
        if not isinstance(event, CameraEvent) or event.kind not in EVENT_TYPES:
            raise ValueError("invalid camera event")
        if event.source != "dvrip-sofia" or event.reason not in {
            "notification", "safety_timeout", "subscription_stopped",
        }:
            raise ValueError("invalid event source/reason")
        device = self.get_device(device_id)
        if device is None:
            raise ValueError("unknown device")
        if event.channel is not None:
            if type(event.channel) is not int:
                raise ValueError("invalid channel")
            channel = self.get_recorder_channel(event.channel)
            if channel is None or int(channel["device_id"]) != int(device_id):
                raise ValueError("channel does not belong to device")
        if event.native_channel is not None and (type(event.native_channel) is not int or not 0 <= event.native_channel <= 255):
            raise ValueError("invalid native channel")
        # timestamp is generated locally, never copied from firmware payload.
        message = json.dumps({
            "source": event.source, "channel_id": event.channel, "native_channel": event.native_channel,
            "reason": event.reason,
        }, ensure_ascii=False, sort_keys=True)
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO events(device_id,site_id,severity,event_type,message,created_at) VALUES(?,?,?,?,?,?)",
                (device_id, device["site_id"], "info", event.kind, message, utcnow()),
            )
        return cursor.lastrowid

    def list_events(self, limit=250):
        return list(
            self.conn.execute(
                """SELECT e.*, d.name device_name
                FROM events e LEFT JOIN devices d ON d.id=e.device_id
                ORDER BY e.id DESC LIMIT ?""",
                (limit,),
            )
        )

    def replace_recorder_channels(self, device_id: int, channels, *, partial: bool = False, _commit: bool = True):
        """Refresh inventory, preserving confirmed video on an incomplete scan."""
        now = utcnow()
        seen: set[int] = set()
        for ch in channels:
            channel_no = int(ch.channel)
            seen.add(channel_no)
            old = self.conn.execute(
                "SELECT * FROM recorder_channels WHERE device_id=? AND channel_no=?",
                (device_id, channel_no),
            ).fetchone()
            if partial and old and not ch.available:
                # A timed-out RTSP attempt does not revoke an earlier verified
                # route. Keep aliases, preferences and the playing channel.
                continue
            source_name = getattr(ch, "source_name", "") or ch.name or f"Canal {channel_no:02d}"
            main_url = getattr(ch, "main_rtsp_url", "") or ch.rtsp_url
            sub_url = getattr(ch, "sub_rtsp_url", "") or ""
            if old:
                self.conn.execute(
                    """UPDATE recorder_channels SET
                    name=?,source_name=?,rtsp_url=?,main_rtsp_url=?,sub_rtsp_url=?,
                    available=?,detail=?,route_kind=?,channel_kind=?,audio_mode=?,audio_codec=?,
                    audio_sample_rate=?,audio_channels=?,audio_detail=?,updated_at=? WHERE id=?""",
                    (
                        source_name,
                        source_name,
                        ch.rtsp_url,
                        main_url,
                        sub_url,
                        int(bool(ch.available)),
                        ch.detail,
                        getattr(ch, "route_kind", "via_recorder"),
                        getattr(ch, "channel_kind", "unknown"),
                        getattr(ch, "audio_mode", "unknown"),
                        getattr(ch, "audio_codec", ""),
                        int(getattr(ch, "audio_sample_rate", 0) or 0),
                        int(getattr(ch, "audio_channels", 0) or 0),
                        getattr(ch, "audio_detail", ""),
                        now,
                        old["id"],
                    ),
                )
            else:
                self.conn.execute(
                    """INSERT INTO recorder_channels(
                    device_id,channel_no,name,source_name,alias,rtsp_url,main_rtsp_url,sub_rtsp_url,
                    preferred_stream,available,detail,route_kind,channel_kind,audio_mode,audio_codec,
                    audio_sample_rate,audio_channels,audio_detail,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        device_id,
                        channel_no,
                        source_name,
                        source_name,
                        "",
                        ch.rtsp_url,
                        main_url,
                        sub_url,
                        "auto",
                        int(bool(ch.available)),
                        ch.detail,
                        getattr(ch, "route_kind", "via_recorder"),
                        getattr(ch, "channel_kind", "unknown"),
                        getattr(ch, "audio_mode", "unknown"),
                        getattr(ch, "audio_codec", ""),
                        int(getattr(ch, "audio_sample_rate", 0) or 0),
                        int(getattr(ch, "audio_channels", 0) or 0),
                        getattr(ch, "audio_detail", ""),
                        now,
                    ),
                )
        # Keep previous channel rows if a transient scan did not see them, but mark
        # them unavailable. This preserves aliases and avoids destructive surprises.
        if seen and not partial:
            placeholders = ",".join("?" for _ in seen)
            self.conn.execute(
                f"UPDATE recorder_channels SET available=0,updated_at=? WHERE device_id=? AND channel_no NOT IN ({placeholders})",
                (now, device_id, *sorted(seen)),
            )
        if _commit:
            self.conn.commit()

    def reconcile_direct_camera_channels(self, device_id, channels, *, diagnostics=(), retirement_evidence=()):
        """Absence/probe failure is not evidence that a known lens disappeared.

        available means a historically confirmed route remains eligible, not
        proof of current health. Current revalidation state is separate metadata.
        Only explicit, reviewed alias evidence can retire a known position.
        """
        from .direct_revalidation import previously_confirmed, DirectChannelRetirement
        previous = self.list_recorder_channels(device_id)
        valid = [channel for channel in channels if channel.available]
        fresh = {channel.channel for channel in valid}
        known = {row["channel_no"]: row for row in previous if previously_confirmed(row)}
        device = self.get_device(device_id)
        if device is None:
            raise ValueError("unknown device")
        try:
            metadata = json.loads(device["metadata_json"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        metadata = metadata if isinstance(metadata, dict) else {}
        old_states = metadata.get("direct_channel_revalidation", {})
        old_states = old_states if isinstance(old_states, dict) else {}
        retired = set()
        for evidence in retirement_evidence:
            if (not isinstance(evidence, DirectChannelRetirement)
                    or evidence.evidence != "operator_confirmed_visual_alias"
                    or evidence.channel not in known
                    or evidence.channel in fresh
                    or evidence.equivalent_channel not in fresh
                    or evidence.channel == evidence.equivalent_channel):
                raise ValueError("insufficient channel retirement evidence")
            retired.add(evidence.channel)
        existing_numbers = {str(row["channel_no"]) for row in previous}
        states = {number: value for number, value in old_states.items() if number in existing_numbers and isinstance(value, dict) and value.get("state") == "retired"}
        for number in fresh | set(known):
            previous_state = old_states.get(str(number), {})
            previous_state = previous_state if isinstance(previous_state, dict) else {}
            was_retired = previous_state.get("state") == "retired"
            if number in retired or (was_retired and number not in fresh):
                state = "retired"
            elif number in fresh:
                state = "validated"
            else:
                attempted = any(item.get("position") == number and item.get("result") == "unconfirmed" for item in diagnostics)
                state = "temporarily_unavailable" if attempted else "pending_revalidation"
            states[str(number)] = {"state": state, "checked_at": utcnow(),
                                   "reason": "operator_confirmed_visual_alias" if state == "retired" else "media_confirmed" if state == "validated" else "scan_inconclusive"}
        # Reuse the existing partial-scan mechanism; no omission invalidates rows.
        with self.conn:
            self.replace_recorder_channels(device_id, valid, partial=True, _commit=False)
            for number, old in known.items():
                if number in fresh:
                    continue
                state = states[str(number)]["state"]
                detail = ("Removido: alias visual confirmado pelo operador • " + old["detail"]) if number in retired else old["detail"]
                self.conn.execute("UPDATE recorder_channels SET available=?,detail=?,updated_at=? WHERE id=?",
                                  (int(state != "retired"), detail, utcnow(), old["id"]))
            metadata["direct_channel_revalidation"] = states
            self.conn.execute("UPDATE devices SET metadata_json=?,updated_at=? WHERE id=?",
                              (json.dumps(metadata, ensure_ascii=False), utcnow(), device_id))
        return states

    def invalidate_direct_camera_channels(self, device_id: int):
        """Mark stale direct-camera streams unavailable after a failed revalidation."""
        self.conn.execute(
            "UPDATE recorder_channels SET available=0,detail=?,updated_at=? WHERE device_id=? AND route_kind='direct'",
            ("Stream direto não validado na última tentativa", utcnow(), int(device_id)),
        )
        self.conn.commit()

    def list_recorder_channels(self, device_id: int, *, available_only: bool = False):
        sql = "SELECT * FROM recorder_channels WHERE device_id=?"
        params = [int(device_id)]
        if available_only:
            sql += " AND available=1"
        sql += " ORDER BY channel_no"
        return list(self.conn.execute(sql, tuple(params)))

    def get_recorder_channel(self, channel_id: int):
        return self.conn.execute("SELECT * FROM recorder_channels WHERE id=?", (int(channel_id),)).fetchone()

    def update_channel_alias(self, channel_id: int, alias: str):
        self.conn.execute(
            "UPDATE recorder_channels SET alias=?,updated_at=? WHERE id=?",
            (alias.strip(), utcnow(), int(channel_id)),
        )
        self.conn.commit()

    def update_channel_preferred_stream(self, channel_id: int, preferred: str):
        preferred = preferred if preferred in {"auto", "sub", "main"} else "auto"
        self.conn.execute(
            "UPDATE recorder_channels SET preferred_stream=?,updated_at=? WHERE id=?",
            (preferred, utcnow(), int(channel_id)),
        )
        self.conn.commit()

    def update_channel_last_good_stream(self, channel_id: int, stream: str):
        stream = stream if stream in {"main", "sub"} else ""
        if not stream:
            return
        self.conn.execute(
            "UPDATE recorder_channels SET last_good_stream=?,updated_at=? WHERE id=?",
            (stream, utcnow(), int(channel_id)),
        )
        self.conn.commit()

    def update_channel_audio(self, channel_id: int, mode: str, codec: str = "", sample_rate: int = 0, channels: int = 0, detail: str = ""):
        mode = mode if mode in {"unknown", "none", "listen", "bidirectional"} else "unknown"
        self.conn.execute(
            """UPDATE recorder_channels SET audio_mode=?,audio_codec=?,audio_sample_rate=?,
               audio_channels=?,audio_detail=?,updated_at=? WHERE id=?""",
            (mode, str(codec or ""), int(sample_rate or 0), int(channels or 0), str(detail or ""), utcnow(), int(channel_id)),
        )
        self.conn.commit()


    def apply_channel_health_samples(self, device_id: int, samples, *, failure_threshold: int = 2):
        """Persist channel health and emit debounced transition events.

        A first negative sample is stored as ``degraded`` and does not generate a
        channel-loss event. The second consecutive negative sample promotes the
        provider state (offline/no_signal). Recovery is immediate once a healthy
        sample is observed. This avoids alert storms during short RTSP reconnects.
        """
        device = self.get_device(int(device_id))
        if not device:
            return
        now = utcnow()
        threshold = max(1, int(failure_threshold or 1))
        for sample in samples:
            channel_no = int(getattr(sample, "channel_no", 0) or 0)
            if channel_no <= 0:
                continue
            row = self.conn.execute(
                "SELECT * FROM recorder_channels WHERE device_id=? AND channel_no=?",
                (int(device_id), channel_no),
            ).fetchone()
            if not row:
                continue
            raw_state = str(getattr(sample, "state", "unknown") or "unknown")
            detail = str(getattr(sample, "detail", "") or "")
            source_ip = str(getattr(sample, "source_ip", "") or "")
            source_port = int(getattr(sample, "source_port", 0) or 0)
            source_protocol = str(getattr(sample, "source_protocol", "") or "")
            old_state = str(row["health_state"] or "unknown")
            old_fail = int(row["health_fail_count"] or 0)
            negative = raw_state in {"offline", "no_signal", "degraded"}
            if raw_state == "ok":
                fail_count = 0
                new_state = "ok"
            elif negative:
                fail_count = old_fail + 1
                if fail_count < threshold and old_state not in {"offline", "no_signal"}:
                    new_state = "degraded"
                else:
                    new_state = raw_state if raw_state != "degraded" else "offline"
            elif raw_state == "unverified":
                # RTSP authentication, timeout or 503 is not native evidence of
                # signal loss. Replace legacy false alarms without claiming OK.
                fail_count = 0
                new_state = "unverified"
            else:
                # An inconclusive provider response must not erase a previously
                # confirmed problem or recovery. Keep the last effective state
                # until a positive/negative observation is obtained.
                fail_count = old_fail
                new_state = old_state if raw_state == "unknown" else raw_state

            changed = new_state != old_state
            last_change = now if changed else str(row["health_last_change_at"] or "")
            last_ok = now if raw_state == "ok" else str(row["health_last_ok_at"] or "")
            # A tentative sample must not turn a short reconnect into a
            # recorded loss/recovery episode. Existing historical values stay.
            confirmed_problem = new_state in {"offline", "no_signal"}
            last_problem = now if confirmed_problem and negative else str(row["health_last_problem_at"] or "")
            self.conn.execute(
                """UPDATE recorder_channels SET health_state=?,health_detail=?,source_ip=?,source_port=?,
                   source_protocol=?,health_fail_count=?,health_last_checked_at=?,health_last_change_at=?,
                   health_last_ok_at=?,health_last_problem_at=? WHERE id=?""",
                (
                    new_state, detail, source_ip or str(row["source_ip"] or ""),
                    source_port or int(row["source_port"] or 0),
                    source_protocol or str(row["source_protocol"] or ""),
                    fail_count, now, last_change, last_ok, last_problem, int(row["id"]),
                ),
            )

            display = self.channel_display_name(row)
            if changed and new_state in {"offline", "no_signal"} and old_state not in {"offline", "no_signal"}:
                if new_state == "offline" and (source_ip or row["source_ip"]):
                    expected = source_ip or str(row["source_ip"] or "")
                    message = f"{device['name']} • {display}: câmera IP configurada {expected} ficou offline/sem mídia."
                elif new_state == "no_signal":
                    message = f"{device['name']} • {display}: perda de sinal/vídeo detectada."
                else:
                    message = f"{device['name']} • {display}: canal indisponível."
                self.conn.execute(
                    """INSERT INTO events(device_id,site_id,severity,event_type,message,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (int(device_id), device["site_id"], "warning", "channel_problem", message, now),
                )
            elif changed and new_state == "ok" and old_state in {"offline", "no_signal"}:
                message = f"{device['name']} • {display}: vídeo/canal restaurado."
                self.conn.execute(
                    """INSERT INTO events(device_id,site_id,severity,event_type,message,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (int(device_id), device["site_id"], "info", "channel_recovered", message, now),
                )
        self.conn.commit()

    def channel_health_summary(self, site_id: int | None = None):
        sql = """SELECT rc.*, d.name device_name, d.status device_status, d.site_id
                 FROM recorder_channels rc JOIN devices d ON d.id=rc.device_id"""
        params = []
        if site_id is not None:
            sql += " WHERE d.site_id=? AND d.archived=0 AND d.correlated_to=0"
            params.append(int(site_id))
        sql += " ORDER BY d.name COLLATE NOCASE, rc.channel_no"
        return list(self.conn.execute(sql, tuple(params)))

    def save_live_workspace(self, site_id: int, grid_count: int, slots: list[dict], ask_stream: bool = False):
        payload = json.dumps(slots, ensure_ascii=False)
        self.conn.execute(
            """INSERT INTO live_workspaces(site_id,grid_count,slots_json,ask_stream,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(site_id) DO UPDATE SET
            grid_count=excluded.grid_count,slots_json=excluded.slots_json,
            ask_stream=excluded.ask_stream,updated_at=excluded.updated_at""",
            (int(site_id), int(grid_count), payload, int(bool(ask_stream)), utcnow()),
        )
        self.conn.commit()

    def list_live_presets(self, site_id: int):
        return list(self.conn.execute(
            "SELECT name,grid_count,updated_at FROM live_presets WHERE site_id=? ORDER BY name COLLATE NOCASE",
            (int(site_id),)))

    def save_live_preset(self, site_id: int, name: str, grid_count: int, slots: list[dict]):
        name = name.strip()
        if not name or len(name) > 64 or int(grid_count) not in (1, 4, 9, 16, 25, 36, 49, 64, 81, 100, 144):
            raise ValueError("Nome ou grade do perfil inválido")
        self.conn.execute(
            """INSERT INTO live_presets(site_id,name,grid_count,slots_json,updated_at) VALUES(?,?,?,?,?)
            ON CONFLICT(site_id,name) DO UPDATE SET grid_count=excluded.grid_count,
            slots_json=excluded.slots_json,updated_at=excluded.updated_at""",
            (int(site_id), name, int(grid_count), json.dumps(slots, ensure_ascii=False), utcnow()))
        self.conn.commit()

    def load_live_preset(self, site_id: int, name: str):
        row = self.conn.execute("SELECT * FROM live_presets WHERE site_id=? AND name=?",
                                (int(site_id), name)).fetchone()
        if not row:
            return None
        slots = json.loads(row["slots_json"])
        return {"name": row["name"], "grid_count": int(row["grid_count"]),
                "slots": slots if isinstance(slots, list) else []}

    def delete_live_preset(self, site_id: int, name: str):
        self.conn.execute("DELETE FROM live_presets WHERE site_id=? AND name=?", (int(site_id), name))
        self.conn.commit()

    def load_live_workspace(self, site_id: int):
        row = self.conn.execute(
            "SELECT * FROM live_workspaces WHERE site_id=?", (int(site_id),)
        ).fetchone()
        if not row:
            return None
        try:
            slots = json.loads(row["slots_json"] or "[]")
        except json.JSONDecodeError:
            slots = []
        return {
            "grid_count": int(row["grid_count"] or 4),
            "slots": slots if isinstance(slots, list) else [],
            "ask_stream": bool(row["ask_stream"]),
        }

    def save_live_window(self, site_id: int, window_key: str, title: str, screen_name: str, geometry: dict, grid_count: int, slots: list[dict], fullscreen: bool = False, enabled: bool = True):
        self.conn.execute(
            """INSERT INTO live_windows(site_id,window_key,title,screen_name,geometry_json,grid_count,slots_json,fullscreen,enabled,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(site_id,window_key) DO UPDATE SET
            title=excluded.title,screen_name=excluded.screen_name,geometry_json=excluded.geometry_json,
            grid_count=excluded.grid_count,slots_json=excluded.slots_json,fullscreen=excluded.fullscreen,
            enabled=excluded.enabled,updated_at=excluded.updated_at""",
            (int(site_id), str(window_key), str(title), str(screen_name), json.dumps(geometry), int(grid_count),
             json.dumps(slots, ensure_ascii=False), int(bool(fullscreen)), int(bool(enabled)), utcnow()),
        )
        self.conn.commit()

    def list_live_windows(self, site_id: int, enabled_only: bool = True):
        query = "SELECT * FROM live_windows WHERE site_id=?"
        params = [int(site_id)]
        if enabled_only:
            query += " AND enabled=1"
        query += " ORDER BY id"
        rows = []
        for row in self.conn.execute(query, params):
            item = dict(row)
            try: item["geometry"] = json.loads(item.get("geometry_json") or "{}")
            except Exception: item["geometry"] = {}
            try: item["slots"] = json.loads(item.get("slots_json") or "[]")
            except Exception: item["slots"] = []
            rows.append(item)
        return rows

    def disable_live_window(self, site_id: int, window_key: str):
        self.conn.execute("UPDATE live_windows SET enabled=0,updated_at=? WHERE site_id=? AND window_key=?", (utcnow(), int(site_id), str(window_key)))
        self.conn.commit()

    @staticmethod
    def channel_display_name(row) -> str:
        return (
            (row["alias"] if "alias" in row.keys() else "")
            or (row["source_name"] if "source_name" in row.keys() else "")
            or row["name"]
            or f"Canal {int(row['channel_no']):02d}"
        )

    def normalize_known_device_classification(self) -> int:
        """Apply conservative fixes to classifications saved by older builds."""
        changed = 0
        rows = list(
            self.conn.execute(
                "SELECT id,kind,manufacturer,provider,model,name,metadata_json FROM devices"
            )
        )
        for row in rows:
            if row["kind"] != "camera":
                continue
            if row["provider"] != "intelbras" and row["manufacturer"].lower() != "intelbras":
                continue
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            ports = metadata.get("open_ports", [])
            evidence = " ".join(metadata.get("evidence", [])).lower()
            model_text = f"{row['model']} {row['name']} {evidence}".lower()
            if 37777 in ports and not any(token in model_text for token in ("vip ", "ip camera", "ipc")):
                self.conn.execute(
                    "UPDATE devices SET kind='xvr',updated_at=? WHERE id=?", (utcnow(), row["id"])
                )
                changed += 1
        # Correct field-validated Aitek cameras that older generic probing may
        # have promoted to NVR/XVR after multiple equivalent RTSP URL hits.
        for row in self.conn.execute("SELECT id,kind,manufacturer,model,name,metadata_json,detected_manufacturer,detected_model,detected_kind FROM devices"):
            text = f"{row['detected_manufacturer']} {row['detected_model']}".lower()
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            evidence = " ".join(metadata.get("evidence", [])).lower()
            if "aitek" in text or "aitek" in evidence:
                if row["kind"] != "camera" or row["manufacturer"] != "Aitek":
                    self.conn.execute("UPDATE devices SET kind='camera',manufacturer='Aitek',provider='aitek',updated_at=? WHERE id=?", (utcnow(), row["id"]))
                    changed += 1
                # Old generic recorder scans could create many false logical
                # channels that all mapped to the same one-sensor camera.
                self.conn.execute("DELETE FROM recorder_channels WHERE device_id=? AND channel_no<>1", (row["id"],))
            ports = set(metadata.get("open_ports", []))
            if 8000 in ports and 554 in ports and (80 in ports or 443 in ports):
                if not row["manufacturer"] or row["manufacturer"].lower() == "hikvision":
                    self.conn.execute("UPDATE devices SET manufacturer='Hikvision',provider='hikvision',updated_at=? WHERE id=?", (utcnow(), row["id"]))
                    changed += 1
        if changed:
            self.conn.commit()
        return changed

    def add_observation(self, device_id, status, latency_ms=None, rtsp_ok=None, http_ok=None):
        self.conn.execute(
            """INSERT INTO observations(device_id,status,latency_ms,rtsp_ok,http_ok,created_at)
            VALUES(?,?,?,?,?,?)""",
            (
                device_id,
                status,
                latency_ms,
                None if rtsp_ok is None else int(rtsp_ok),
                None if http_ok is None else int(http_ok),
                utcnow(),
            ),
        )
        self.conn.commit()

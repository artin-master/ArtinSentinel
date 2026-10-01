"""Read the official shared AKDB catalog for device identification."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import sqlite3

from artin_akdb import CORE_RECORDS, default_store_path
from artin_akdb.sync import knowledge_record_from_dict


@lru_cache(maxsize=4)
def _read_snapshot(path: str, mtime: int, wal_mtime: int):
    records = {row.stable_id: row for row in CORE_RECORDS}
    try:
        connection = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=0.5)
        try:
            rows = connection.execute("SELECT stable_id,revision,payload_json FROM records LIMIT 2000").fetchall()
        finally:
            connection.close()
        for stable_id, revision, payload_json in rows:
            try:
                payload = json.loads(payload_json)
                record = knowledge_record_from_dict(payload)
                if record.stable_id != stable_id or not record.manufacturer or "sentinel" not in record.domains:
                    continue
                packaged = records.get(stable_id)
                if packaged is None or int(revision) > packaged.revision:
                    records[stable_id] = record
            except (TypeError, ValueError, KeyError):
                continue
    except (OSError, sqlite3.Error):
        pass
    return tuple(records.values())


def effective_core_records():
    path = default_store_path().resolve()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return CORE_RECORDS
    try:
        wal_mtime = Path(str(path) + "-wal").stat().st_mtime_ns
    except OSError:
        wal_mtime = 0
    return _read_snapshot(str(path), mtime, wal_mtime)

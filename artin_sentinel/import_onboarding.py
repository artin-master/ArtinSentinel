"""Post-import inventory helpers.

This module is deliberately UI-independent so transfer recovery can be tested
without starting Qt. Import never duplicates an existing device; onboarding only
reveals and validates the already-resolved record.
"""
from __future__ import annotations


def configuration_devices(db, current_site_id, scope="active"):
    """Return administrative inventory without changing the active monitoring Site."""
    return db.list_devices(None) if str(scope) == "all" else db.list_devices(current_site_id)


def target_device_ids(preview):
    """Return non-conflicting records represented by an import after it is applied."""
    seen = set()
    result = []
    for row in (preview or {}).get("rows", ()):
        if row.get("status") != "existing":
            continue
        device_id = row.get("target_device_id")
        if device_id is None:
            continue
        device_id = int(device_id)
        if device_id not in seen:
            seen.add(device_id)
            result.append(device_id)
    return result


def _has_validated_route(rows):
    for row in rows:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        for field in ("rtsp_url", "main_rtsp_url", "sub_rtsp_url"):
            if field in keys and str(row[field] or "").strip():
                return True
    return False


def device_needs_setup(db, device_id):
    device = db.get_device(int(device_id))
    if not device or bool(device["archived"]):
        return False
    kind = str(device["kind"] or "").lower()
    if kind not in {"camera", "dvr", "nvr", "xvr"}:
        return False
    channels = db.list_recorder_channels(int(device_id))
    # Portable files intentionally omit passwords and authenticated media URLs.
    # Imported channel names/layouts therefore do not prove that this PC can
    # actually access the device.
    return (not bool(device["credential_saved"])) or (not _has_validated_route(channels))


def devices_needing_setup(db, device_ids):
    result = []
    seen = set()
    for raw in device_ids or ():
        device_id = int(raw)
        if device_id in seen:
            continue
        seen.add(device_id)
        if device_needs_setup(db, device_id):
            result.append(device_id)
    return result

"""Portable inventory/layout file without secrets or authenticated media routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

FORMAT = "artin-sentinel-portable-v1"


def _slots(db, slots):
    result = []
    for slot in slots:
        if not isinstance(slot, dict) or slot.get("type") != "channel":
            result.append({})
            continue
        device = db.get_device(int(slot.get("device_id") or 0))
        channel = db.get_recorder_channel(int(slot.get("channel_id") or 0))
        if not device or not channel or int(channel["device_id"]) != int(device["id"]):
            result.append({})
            continue
        result.append({
            "ip": device["ip"], "channel_no": int(channel["channel_no"]),
            "forced_stream": slot.get("forced_stream") if slot.get("forced_stream") in {"main", "sub"} else "",
            "display_mode": slot.get("display_mode") if slot.get("display_mode") in {"fit", "fill", "original"} else "fit",
        })
    return result


def export_configuration(db):
    sites = []
    for site in db.list_sites(include_archived=False):
        devices = []
        for device in db.list_devices(int(site["id"])):
            channels = [{
                "channel_no": int(ch["channel_no"]), "name": ch["name"],
                "alias": ch["alias"], "preferred_stream": ch["preferred_stream"],
            } for ch in db.list_recorder_channels(int(device["id"]))]
            devices.append({key: device[key] for key in
                            ("name", "ip", "port", "manufacturer", "model", "kind", "provider")}
                           | {"channels": channels})
        workspace = db.load_live_workspace(int(site["id"]))
        windows = db.list_live_windows(int(site["id"]))
        sites.append({
            "name": site["name"], "description": site["description"], "devices": devices,
            "workspace": ({"grid_count": workspace["grid_count"],
                           "slots": _slots(db, workspace["slots"])} if workspace else None),
            "windows": [{"key": row["window_key"], "title": row["title"],
                         "grid_count": row["grid_count"], "slots": _slots(db, row["slots"])}
                        for row in windows],
        })
    return {"format": FORMAT, "exported_at": datetime.now(timezone.utc).isoformat(),
            "notice": "Sem credenciais e URLs de stream. Reconfigure a senha e leia os canais no destino.",
            "sites": sites}


def _text(value, limit=256):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Texto inválido ou longo demais no arquivo portátil")
    return value.strip()


def _restore_slots(slots, channels):
    result = []
    if not isinstance(slots, list) or len(slots) > 144:
        raise ValueError("Layout inválido")
    for slot in slots:
        if not slot:
            result.append({})
            continue
        if not isinstance(slot, dict):
            raise ValueError("Janela inválida no layout")
        key = (_text(slot.get("ip")), int(slot.get("channel_no") or 0))
        ids = channels.get(key)
        result.append({"type": "channel", "device_id": ids[0], "channel_id": ids[1],
                       "forced_stream": slot.get("forced_stream") if slot.get("forced_stream") in {"main", "sub"} else "",
                       "display_mode": slot.get("display_mode") if slot.get("display_mode") in {"fit", "fill", "original"} else "fit"}
                      if ids else {})
    return result


def import_configuration(db, payload):
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError("Formato de configuração não reconhecido")
    sites = payload.get("sites")
    if not isinstance(sites, list) or len(sites) > 100:
        raise ValueError("Lista de Sites inválida")
    # Validate the entire input before the first write. The savepoint also
    # protects against database errors and keeps existing records untouched.
    plan = []
    for site in sites:
        if not isinstance(site, dict): raise ValueError("Site inválido")
        name = _text(site.get("name"))
        if not name: raise ValueError("Site sem nome")
        devices = site.get("devices")
        windows = site.get("windows", [])
        if not isinstance(devices, list) or len(devices) > 2000 or not isinstance(windows, list) or len(windows) > 30:
            raise ValueError("Inventário ou janelas inválidas")
        for dev in devices:
            if not isinstance(dev, dict) or not _text(dev.get("ip")):
                raise ValueError("Equipamento inválido")
            channels = dev.get("channels", [])
            if not isinstance(channels, list) or len(channels) > 256:
                raise ValueError("Canais inválidos")
            for ch in channels:
                if not isinstance(ch, dict) or not 1 <= int(ch.get("channel_no") or 0) <= 256:
                    raise ValueError("Número de canal inválido")
                for key in ("name", "alias"):
                    _text(ch.get(key, ""))
            for key in ("name", "manufacturer", "model", "kind", "provider"):
                _text(dev.get(key, ""))
        workspace = site.get("workspace")
        if workspace is not None and not isinstance(workspace, dict): raise ValueError("Workspace inválido")
        for layout in ([workspace] if workspace else []) + windows:
            if not isinstance(layout, dict) or not 1 <= int(layout.get("grid_count") or 0) <= 144:
                raise ValueError("Grade inválida")
            slots = layout.get("slots")
            if not isinstance(slots, list) or len(slots) > 144:
                raise ValueError("Posições inválidas")
        plan.append((name, site, devices, workspace, windows))
    counts = {"sites": 0, "devices": 0, "channels": 0, "layouts": 0}
    now = datetime.now(timezone.utc).isoformat()
    db.conn.execute("SAVEPOINT portable_import")
    try:
        for name, site, devices, workspace, windows in plan:
            row = db.conn.execute("SELECT id FROM sites WHERE name=?", (name,)).fetchone()
            if row: site_id = int(row[0])
            else:
                cur = db.conn.execute("INSERT INTO sites(name,description,created_at) VALUES(?,?,?)",
                                      (name, _text(site.get("description", ""), 1024), now))
                site_id = int(cur.lastrowid); counts["sites"] += 1
            ids = {}
            for dev in devices:
                ip = _text(dev["ip"])
                row = db.conn.execute("SELECT id FROM devices WHERE site_id=? AND ip=?", (site_id, ip)).fetchone()
                if row: did = int(row[0])
                else:
                    cur = db.conn.execute(
                        """INSERT INTO devices(site_id,name,ip,port,manufacturer,model,kind,provider,status,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (site_id, _text(dev.get("name", "")) or ip, ip, dev.get("port"),
                         _text(dev.get("manufacturer", "")), _text(dev.get("model", "")),
                         _text(dev.get("kind", "unknown")), _text(dev.get("provider", "generic")),
                         "unknown", now, now))
                    did = int(cur.lastrowid); counts["devices"] += 1
                for ch in dev.get("channels", []):
                    no = int(ch["channel_no"])
                    row = db.conn.execute("SELECT id FROM recorder_channels WHERE device_id=? AND channel_no=?", (did, no)).fetchone()
                    if row: cid = int(row[0])
                    else:
                        cur = db.conn.execute(
                            """INSERT INTO recorder_channels(device_id,channel_no,name,alias,preferred_stream,updated_at)
                            VALUES(?,?,?,?,?,?)""",
                            (did, no, _text(ch.get("name", "")), _text(ch.get("alias", "")),
                             ch.get("preferred_stream") if ch.get("preferred_stream") in {"auto", "main", "sub"} else "auto", now))
                        cid = int(cur.lastrowid); counts["channels"] += 1
                    ids[(ip, no)] = (did, cid)
            if workspace and not db.conn.execute("SELECT 1 FROM live_workspaces WHERE site_id=?", (site_id,)).fetchone():
                slots = _restore_slots(workspace["slots"], ids)
                db.conn.execute("INSERT INTO live_workspaces(site_id,grid_count,slots_json,updated_at) VALUES(?,?,?,?)",
                                (site_id, int(workspace["grid_count"]), json.dumps(slots), now))
                counts["layouts"] += 1
            for window in windows:
                key = _text(window.get("key", ""))
                if not key or db.conn.execute("SELECT 1 FROM live_windows WHERE site_id=? AND window_key=?", (site_id, key)).fetchone():
                    continue
                slots = _restore_slots(window["slots"], ids)
                db.conn.execute(
                    """INSERT INTO live_windows(site_id,window_key,title,grid_count,slots_json,enabled,updated_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (site_id, key, _text(window.get("title", "Monitoramento")), int(window["grid_count"]),
                     json.dumps(slots), 1, now))
                counts["layouts"] += 1
        db.conn.execute("RELEASE SAVEPOINT portable_import")
    except Exception:
        db.conn.execute("ROLLBACK TO SAVEPOINT portable_import")
        db.conn.execute("RELEASE SAVEPOINT portable_import")
        raise
    return counts

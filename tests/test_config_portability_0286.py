import json
import tempfile
import unittest
from pathlib import Path

from artin_sentinel.config_portability import export_configuration, import_configuration
from artin_sentinel.db import Database


class PortabilityTest(unittest.TestCase):
    def test_roundtrip_omits_authenticated_routes_and_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Database(Path(folder) / "source.db")
            target = Database(Path(folder) / "target.db")
            try:
                site_id = source.add_site("Casa", "Teste")
                now = "2026-09-29T00:00:00+00:00"
                source.conn.execute(
                    """INSERT INTO devices(site_id,name,ip,kind,provider,status,rtsp_url,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (site_id, "PTZ", "192.0.2.9", "camera", "intelbras", "online",
                     "rtsp://admin:private-password@192.0.2.9/live", now, now))
                did = source.conn.execute("SELECT id FROM devices WHERE ip='192.0.2.9'").fetchone()[0]
                source.conn.execute(
                    "INSERT INTO recorder_channels(device_id,channel_no,name,alias,rtsp_url,updated_at) VALUES(?,?,?,?,?,?)",
                    (did, 1, "CAM 1", "Portão", "rtsp://admin:private-password@192.0.2.9/live", now))
                cid = source.conn.execute("SELECT id FROM recorder_channels WHERE device_id=?", (did,)).fetchone()[0]
                source.save_live_workspace(site_id, 4, [{"type": "channel", "device_id": did, "channel_id": cid}])
                exported = export_configuration(source)
                raw = json.dumps(exported)
                self.assertNotIn("private-password", raw)
                self.assertNotIn("rtsp://", raw)
                self.assertEqual(import_configuration(target, exported),
                                 {"sites": 1, "devices": 1, "channels": 1, "layouts": 1})
                self.assertEqual(import_configuration(target, exported),
                                 {"sites": 0, "devices": 0, "channels": 0, "layouts": 0})
                imported_site = target.conn.execute("SELECT id FROM sites WHERE name='Casa'").fetchone()[0]
                imported = target.list_devices(imported_site)[0]
                self.assertEqual(imported["rtsp_url"], "")
                self.assertEqual(imported["status"], "unknown")
                self.assertEqual(target.load_live_workspace(imported_site)["slots"][0]["device_id"], imported["id"])
            finally:
                source.close()
                target.close()


if __name__ == "__main__":
    unittest.main()

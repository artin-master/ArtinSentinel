from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from artin_sentinel.channel_health import _fallback_rtsp_sample, ChannelHealthSample, HEALTH_OFFLINE, HEALTH_UNVERIFIED
from artin_sentinel.db import Database


class InconclusiveHealthTest(TestCase):
    def test_rtsp_503_does_not_prove_signal_loss_and_clears_old_label(self):
        with TemporaryDirectory() as temp:
            db = Database(Path(temp) / "db.sqlite3")
            now = "2026-09-20T00:00:00+00:00"
            db.conn.execute("INSERT INTO sites(name,created_at) VALUES(?,?)", ("Site", now))
            sid = db.conn.execute("SELECT id FROM sites").fetchone()[0]
            db.conn.execute("""INSERT INTO devices(site_id,name,ip,kind,provider,status,created_at,updated_at)
                               VALUES(?,?,?,?,?,?,?,?)""", (sid, "DVR", "192.0.2.1", "dvr", "intelbras", "online", now, now))
            did = db.conn.execute("SELECT id FROM devices").fetchone()[0]
            db.conn.execute("""INSERT INTO recorder_channels(device_id,channel_no,name,rtsp_url,available,channel_kind,updated_at)
                               VALUES(?,?,?,?,?,?,?)""", (did, 1, "CAM 1", "rtsp://192.0.2.1/cam1", 1, "analog", now))
            db.conn.commit()
            db.apply_channel_health_samples(did, [ChannelHealthSample(1, HEALTH_OFFLINE, "old")], failure_threshold=1)
            with patch("artin_sentinel.channel_health.probe_rtsp_url_detailed", return_value=SimpleNamespace(
                    ok=False, detail="503", safe_summary=lambda: "primeira resposta 503")):
                sample = _fallback_rtsp_sample(db.list_recorder_channels(did)[0], "admin", "pw")
            self.assertEqual(sample.state, HEALTH_UNVERIFIED)
            db.apply_channel_health_samples(did, [sample])
            self.assertEqual(db.list_recorder_channels(did)[0]["health_state"], HEALTH_UNVERIFIED)
            self.assertEqual(len(db.list_events()), 1)
            db.close()

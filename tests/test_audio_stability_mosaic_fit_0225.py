import json
from pathlib import Path
from types import SimpleNamespace

import artin_sentinel.live as live
from artin_sentinel import __version__
from artin_sentinel.akdb import audio_capability
from artin_sentinel.db import Database
from artin_akdb import CORE_REVISION, record_by_legacy_key


def test_release_0225_and_akdb_talkback_is_conservative():
    assert __version__ == "0.2.91"
    assert CORE_REVISION >= 7
    audio = audio_capability(profile_key="it-blue-x3-we2q")
    assert audio["mode"] == "bidirectional"
    assert audio["talkback_protocol"] == "xm-dvrip-g711a-experimental"
    core = record_by_legacy_key("it-blue-x3-we2q")
    assert core is not None
    assert "xm-dvrip-talkback-not-field-validated" in core.negative_knowledge


def test_dynamic_volume_uses_pactl_sink_input_without_rtsp_restart(monkeypatch):
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/pactl" if name == "pactl" else None)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:5] == ["/usr/bin/pactl", "-f", "json", "list", "sink-inputs"]:
            payload = [{"index": 42, "properties": {"application.process.id": "1234"}}]
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if cmd[:2] == ["/usr/bin/pactl", "set-sink-input-volume"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(cmd)

    monkeypatch.setattr(live.subprocess, "run", fake_run)
    ok, detail = live.set_process_audio_gain(1234, 100)
    assert ok
    assert "200%" in detail
    assert ["/usr/bin/pactl", "set-sink-input-volume", "42", "200%"] in calls


def test_live_audio_volume_method_does_not_stop_or_restart(monkeypatch):
    sess = live.LiveAudioSession("rtsp://camera/main", volume=75)
    class Proc:
        pid = 1234
        def poll(self): return None
    sess._process = Proc()
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/pactl" if name == "pactl" else None)
    # Do not execute a real controller thread; prove the public setter never calls stop/start.
    monkeypatch.setattr(sess, "stop", lambda: (_ for _ in ()).throw(AssertionError("stop called")))
    monkeypatch.setattr(sess, "start", lambda: (_ for _ in ()).throw(AssertionError("start called")))
    sess.restart_with_volume(90)
    assert sess.volume == 90


def test_channel_runtime_cache_and_audio_metadata_columns(tmp_path):
    db = Database(tmp_path / "sentinel.db")
    try:
        columns = {r[1] for r in db.conn.execute("PRAGMA table_info(recorder_channels)")}
        assert "last_good_stream" in columns
        now = "2026-09-20T00:00:00+00:00"
        db.conn.execute("INSERT INTO sites(name,created_at) VALUES(?,?)", ("Site", now))
        site_id = db.conn.execute("SELECT id FROM sites").fetchone()[0]
        db.conn.execute(
            """INSERT INTO devices(site_id,name,ip,kind,provider,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (site_id, "DVR", "192.0.2.10", "xvr", "intelbras", "online", now, now),
        )
        did = db.conn.execute("SELECT id FROM devices").fetchone()[0]
        db.conn.execute(
            """INSERT INTO recorder_channels(device_id,channel_no,name,rtsp_url,available,updated_at)
               VALUES(?,?,?,?,?,?)""",
            (did, 5, "CAM 05", "rtsp://192.0.2.10/ch5", 1, now),
        )
        db.conn.commit()
        cid = db.conn.execute("SELECT id FROM recorder_channels").fetchone()[0]
        db.update_channel_last_good_stream(cid, "main")
        db.update_channel_audio(cid, "listen", "pcm_alaw", 8000, 1, "field")
        row = db.get_recorder_channel(cid)
        assert row["last_good_stream"] == "main"
        assert row["audio_mode"] == "listen"
        assert row["audio_codec"] == "pcm_alaw"
        assert row["audio_sample_rate"] == 8000
    finally:
        db.close()


def test_mosaic_fill_mode_and_audio_status_bar_are_wired():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'self._display_mode = "fill"' in source
    assert "Qt.KeepAspectRatioByExpanding" in source
    assert '"Preencher (sem esticar)"' in source
    assert '"display_mode": source.get("display_mode") or tile.display_mode' in source
    assert 'self.bottom_audio = QLabel("Áudio: desligado")' in source
    assert 'self.live_audio_identity = self._audio_identity_text(device, channel)' in source
    assert 'session.set_volume(value)' in source
    assert 'session.restart_with_volume(value)' not in source


def test_mhdx_legacy_channels_are_a_real_phase_before_hybrid_scan():
    source = Path("artin_sentinel/recorder.py").read_text(encoding="utf-8")
    legacy = source.index("run_batch(legacy_batch, 4)")
    hybrid = source.index("run_batch(hybrid_batch, 2)")
    assert legacy < hybrid
    assert "no hybrid/IP probe is started until" in source

from pathlib import Path
from types import SimpleNamespace

import artin_sentinel.channel_health as health
from artin_sentinel import __version__
from artin_sentinel.db import Database


def _seed_db(tmp_path):
    db = Database(tmp_path / "sentinel.db")
    now = "2026-09-20T00:00:00+00:00"
    db.conn.execute("INSERT INTO sites(name,created_at) VALUES(?,?)", ("Site", now))
    site_id = db.conn.execute("SELECT id FROM sites WHERE name='Site'").fetchone()[0]
    db.conn.execute(
        """INSERT INTO devices(site_id,name,ip,kind,provider,status,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (site_id, "DVR", "192.0.2.10", "dvr", "hikvision", "online", now, now),
    )
    did = db.conn.execute("SELECT id FROM devices WHERE name='DVR'").fetchone()[0]
    db.conn.execute(
        """INSERT INTO recorder_channels(device_id,channel_no,name,rtsp_url,available,channel_kind,updated_at)
           VALUES(?,?,?,?,?,?,?)""",
        (did, 17, "CAM 17", "rtsp://192.0.2.10/Streaming/Channels/1701", 1, "ip", now),
    )
    db.conn.commit()
    return db, site_id, did


def test_version_and_health_columns_0226(tmp_path):
    assert __version__ == "0.2.86"
    db, _, _ = _seed_db(tmp_path)
    try:
        columns = {r[1] for r in db.conn.execute("PRAGMA table_info(recorder_channels)")}
        for name in {
            "health_state", "health_detail", "source_ip", "source_port", "source_protocol",
            "health_fail_count", "health_last_checked_at", "health_last_change_at",
            "health_last_ok_at", "health_last_problem_at",
        }:
            assert name in columns
    finally:
        db.close()


def test_channel_problem_is_debounced_and_recovery_emits_event(tmp_path):
    db, _, did = _seed_db(tmp_path)
    try:
        bad = health.ChannelHealthSample(
            17, health.HEALTH_OFFLINE, "ISAPI canal IP • offline",
            source_ip="192.168.15.3", source_port=80, source_protocol="ONVIF", authoritative=True, media_ok=False,
        )
        db.apply_channel_health_samples(did, [bad], failure_threshold=2)
        row = db.list_recorder_channels(did)[0]
        assert row["health_state"] == "degraded"
        assert row["source_ip"] == "192.168.15.3"
        assert db.list_events() == []

        db.apply_channel_health_samples(did, [bad], failure_threshold=2)
        row = db.list_recorder_channels(did)[0]
        assert row["health_state"] == "offline"
        events = db.list_events()
        assert events[0]["event_type"] == "channel_problem"
        assert "192.168.15.3" in events[0]["message"]

        good = health.ChannelHealthSample(
            17, health.HEALTH_OK, "ISAPI canal IP • online",
            source_ip="192.168.15.3", source_port=80, source_protocol="ONVIF", authoritative=True, media_ok=True,
        )
        db.apply_channel_health_samples(did, [good], failure_threshold=2)
        row = db.list_recorder_channels(did)[0]
        assert row["health_state"] == "ok"
        events = db.list_events()
        assert events[0]["event_type"] == "channel_recovered"
    finally:
        db.close()


def test_hikvision_native_status_exposes_configured_ip(monkeypatch):
    monkeypatch.setattr(health, "probe_hikvision_isapi_video_inputs", lambda *a, **k: SimpleNamespace(
        authenticated=True,
        inputs=(SimpleNamespace(channel_id=1, enabled=True, resolution_description="1080P"),),
    ))
    monkeypatch.setattr(health, "probe_hikvision_input_proxy_status", lambda *a, **k: SimpleNamespace(
        authenticated=True,
        channels=(SimpleNamespace(
            channel_id=17, online=False, ip_address="192.168.15.3", port=80,
            protocol="ONVIF", detect_result="unknownError",
        ),),
    ))
    rows = health.probe_recorder_channel_health(
        "hikvision", "192.0.2.10", "admin", "pw",
        [
            {"channel_no": 1, "main_rtsp_url": "rtsp://x/101", "channel_kind": "analog"},
            {"channel_no": 17, "main_rtsp_url": "rtsp://x/1701", "channel_kind": "ip"},
        ],
    )
    by_no = {r.channel_no: r for r in rows}
    assert by_no[1].state == health.HEALTH_OK
    assert by_no[17].state == health.HEALTH_OFFLINE
    assert by_no[17].source_ip == "192.168.15.3"
    assert by_no[17].source_protocol == "ONVIF"
    assert by_no[17].authoritative is True


def test_generic_health_probe_is_lightweight_no_ffprobe(monkeypatch):
    calls = []
    def fake_probe(url, username, password, timeout=1.25, use_ffprobe=True):
        calls.append((url, timeout, use_ffprobe))
        return SimpleNamespace(ok=True, detail="SDP OK", safe_summary=lambda: "SDP OK")
    monkeypatch.setattr(health, "probe_rtsp_url_detailed", fake_probe)
    rows = health.probe_recorder_channel_health(
        "intelbras", "192.0.2.20", "admin", "pw",
        [{"channel_no": 5, "main_rtsp_url": "rtsp://dvr/main5", "sub_rtsp_url": "rtsp://dvr/sub5", "last_good_stream": "main", "channel_kind": "ip"}],
    )
    assert rows[0].state == health.HEALTH_OK
    assert calls == [("rtsp://dvr/main5", 1.0, False)]


def test_ui_wires_channel_health_after_recorder_is_online():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "self.start_channel_health_check(int(device_id))" in source
    assert "failure_threshold=2" in source
    assert 'self.channel_health_table = QTableWidget(0, 8)' in source
    assert '"IP configurado"' in source
    assert '"channel_problem"' in Path("artin_sentinel/db.py").read_text(encoding="utf-8")

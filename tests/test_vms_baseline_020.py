from pathlib import Path

from artin_sentinel.db import Database
from artin_sentinel.live import LiveStreamSession, sanitize_text


def test_workspace_roundtrip(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site_id = db.list_sites()[0]["id"]
    slots = [
        {"type": "channel", "device_id": 1, "channel_id": 2, "forced_stream": "sub"},
        {},
        {"type": "channel", "device_id": 3, "channel_id": 4, "forced_stream": ""},
        {},
    ]
    db.save_live_workspace(site_id, 4, slots, True)
    state = db.load_live_workspace(site_id)
    assert state["grid_count"] == 4
    assert state["ask_stream"] is True
    assert state["slots"][0]["forced_stream"] == "sub"
    db.close()


def test_sanitize_rtsp_credentials():
    line = "error opening rtsp://admin:supersecret@192.168.1.10:554/cam/realmonitor"
    clean = sanitize_text(line)
    assert "supersecret" not in clean
    assert "admin" not in clean
    assert "***:***@" in clean


def test_live_session_profiles_are_recorded():
    s = LiveStreamSession(
        "rtsp://192.168.1.10/main",
        "admin",
        "pw",
        profile_name="Substream",
        fallback_url="rtsp://192.168.1.10/main",
        fallback_name="Main stream",
    )
    assert s.profile_name == "Substream"
    assert s.fallback_name == "Main stream"
    assert s.attempts == 0

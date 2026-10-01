from pathlib import Path

from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.ip_camera import _candidate_pairs
from artin_sentinel.recorder import intelbras_channel_url_variants


def test_direct_camera_candidate_pairs_include_provider_paths():
    pairs = _candidate_pairs("192.0.2.10", "hikvision")
    assert any("/Streaming/Channels/101" in main for _label, main, _sub in pairs)
    pairs = _candidate_pairs("192.0.2.10", "intelbras-mibo")
    assert any("/cam/realmonitor?channel=1&subtype=0" in main for _label, main, _sub in pairs)


def test_intelbras_variants_cover_both_query_orders():
    urls = intelbras_channel_url_variants("192.0.2.20", 5, 0)
    assert any("channel=5&subtype=0" in url for url in urls)
    assert any("subtype=0&channel=5" in url for url in urls)


def test_multi_monitor_workspace_persists(tmp_path: Path):
    db = Database(tmp_path / "sentinel.db")
    site = db.list_sites()[0]
    db.save_live_window(
        site["id"], "monitor-1", "Monitoramento", "HDMI-1",
        {"x": 10, "y": 20, "w": 1000, "h": 700}, 9,
        [{"type": "channel", "device_id": 1, "channel_id": 2}], False, True,
    )
    rows = db.list_live_windows(site["id"])
    assert len(rows) == 1
    assert rows[0]["window_key"] == "monitor-1"
    assert rows[0]["grid_count"] == 9
    assert rows[0]["geometry"]["w"] == 1000
    db.disable_live_window(site["id"], "monitor-1")
    assert db.list_live_windows(site["id"]) == []
    db.close()


def test_direct_camera_channel_route_fields_survive_db(tmp_path: Path):
    from artin_sentinel.recorder import RecorderChannel
    db = Database(tmp_path / "sentinel.db")
    site = db.list_sites()[0]
    did = db.upsert_device(Device(site_id=site["id"], name="Camera", ip="192.0.2.30", kind=DeviceKind.CAMERA))
    ch = RecorderChannel(
        1, "Camera 01", "rtsp://192.0.2.30/main", True,
        source_name="Camera 01", main_rtsp_url="rtsp://192.0.2.30/main",
        sub_rtsp_url="rtsp://192.0.2.30/sub", route_kind="direct", channel_kind="ip",
    )
    db.replace_recorder_channels(did, [ch])
    row = db.list_recorder_channels(did)[0]
    assert row["route_kind"] == "direct"
    assert row["channel_kind"] == "ip"
    db.close()


def test_app_source_contains_double_click_edit_and_detached_window():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "cellDoubleClicked.connect" in source
    assert "class DetachedMonitorWindow" in source
    assert "Nova janela de monitoramento" in source
    assert "Tela cheia do mosaico" in source
    assert "Testar stream" in source

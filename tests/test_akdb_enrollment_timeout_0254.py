import time
from types import SimpleNamespace

from artin_sentinel.akdb import recorder_scan_capacity_for_device
from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.recorder import RecorderChannel, RtspProbeReport, scan_intelbras_channels


def test_akdb_recovers_legacy_five_channel_cap_and_respects_manual_override():
    defaults = (("NVD 1416", "intelbras-nvd-1416", 16),
                ("NVD 1516", "intelbras-nvd-1516", 16),
                ("MHDX 1216", "intelbras-mhdx-1216", 16),
                ("MHDX 1004", "intelbras-mhdx", 5))
    for model, key, expected in defaults:
        assert recorder_scan_capacity_for_device(provider="intelbras", profile_key=key,
                                                 model=model, saved_source="akdb", saved_limit=5) == expected
    assert recorder_scan_capacity_for_device(provider="intelbras", profile_key="intelbras-nvd-1416",
                                             model="Intelbras", saved_limit=5) == 16
    assert recorder_scan_capacity_for_device(provider="intelbras", profile_key="intelbras-nvd-1416",
                                             model="NVD 1416", saved_source="manual", saved_limit=8) == 8


def test_timed_out_scan_lists_pending_positions_without_claiming_video(monkeypatch):
    from artin_sentinel import recorder

    inventory = SimpleNamespace(channels=[SimpleNamespace(channel_id=1, name="Entrada")],
                                ok=True, authenticated=True, detail="CGI OK")
    monkeypatch.setattr(recorder, "probe_intelbras_channel_titles", lambda *_a, **_k: inventory)
    monkeypatch.setattr(recorder, "_select_stream_profile", lambda *_a, **_k: (1, 0, "RTSP", "rtsp://seed"))

    def slow_probe(*_args, **_kwargs):
        time.sleep(0.02)
        return RtspProbeReport(False, 404, "sem mídia", first_status=404)

    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", slow_probe)
    result = scan_intelbras_channels("192.0.2.8", "admin", "password", max_channels=16,
                                    max_seconds=0.005, channel_layout="nvr")
    assert result.partial and result.untested > 0
    assert [row.channel for row in result] == list(range(1, 17))
    assert not any(row.available for row in result)
    assert any("ainda não testado" in row.detail for row in result)


def test_partial_inventory_adds_new_positions_without_erasing_playing_channel(tmp_path):
    db = Database(tmp_path / "sentinel.db")
    try:
        site = db.list_sites()[0]["id"]
        did = db.upsert_device(Device(site_id=site, name="NVD 1416", ip="192.0.2.8",
                                      kind=DeviceKind.NVR, manufacturer="Intelbras",
                                      model="NVD 1416", provider="intelbras"))
        old_url = "rtsp://192.0.2.8/cam/realmonitor?channel=1&subtype=0"
        db.replace_recorder_channels(did, [RecorderChannel(1, "Canal 1", old_url, True)])
        db.replace_recorder_channels(did, [
            RecorderChannel(1, "Canal 1", old_url, False, detail="tempo limite"),
            RecorderChannel(2, "Canal 2", "rtsp://192.0.2.8/2", False, detail="não testado"),
        ], partial=True)
        rows = db.list_recorder_channels(did)
        assert [row["channel_no"] for row in rows] == [1, 2]
        assert bool(rows[0]["available"]) and rows[0]["rtsp_url"] == old_url
        assert not bool(rows[1]["available"])
    finally:
        db.close()

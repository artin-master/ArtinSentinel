from types import SimpleNamespace

from artin_sentinel import ip_camera
from artin_sentinel.db import Database, changed_channel_routes
from artin_sentinel.domain import Device


def test_moving_ptz_cannot_certify_another_lens(monkeypatch):
    accepted = iter((0xFFFF, 0xAAAA, 0x5555))
    monkeypatch.setattr(ip_camera, "_video_frame_signature",
                        lambda url, *a, **k: 0 if url == "candidate" else next(accepted))
    monkeypatch.setattr(ip_camera.time, "sleep", lambda *_: None)
    assert ip_camera._paired_visual_alias("candidate", ["ptz"], "u", "p", threshold=4)


def test_rtsp_alias_is_replaced_by_fixed_native_hardware_slot(monkeypatch):
    monkeypatch.setattr(ip_camera, "dvrip_multilens_hints", lambda *a, **k: {})
    monkeypatch.setattr(ip_camera, "validate_rtsp_media",
                        lambda url, *a, **k: ("_channel=0_stream=0" in url or "_channel=1_stream=0" in url, "video"))
    monkeypatch.setattr(ip_camera, "_video_frame_signature",
                        lambda url, *a, **k: 0 if "_channel=0_" in url else (1 << 100))
    monkeypatch.setattr(ip_camera, "_paired_visual_alias", lambda *a, **k: False)
    monkeypatch.setattr(ip_camera, "_direct_audio_fields", lambda *a, **k: {})
    monkeypatch.setattr(ip_camera, "probe_dvrip_media",
                        lambda *a, channel=0, subtype=0, **k: SimpleNamespace(
                            ok=(channel == 1 and subtype == 0), codec="h264", detail="verified"))
    monkeypatch.setattr(ip_camera, "dvrip_frame_signature", lambda *a, **k: (1 << 120))
    channels = ip_camera._scan_itblue_x3_multilens_rtsp("192.0.2.47", "u", "p")
    assert [(ch.channel, ch.source_name) for ch in channels] == [(1, "Lente PTZ"), (2, "Lente fixa 1")]
    assert "_channel=0_" in channels[0].rtsp_url
    assert channels[1].rtsp_url.startswith("dvrip://")
    assert "channel=1" in channels[1].rtsp_url


def test_native_fixed_channel_repeating_ptz_is_not_promoted(monkeypatch):
    monkeypatch.setattr(ip_camera, "dvrip_multilens_hints", lambda *a, **k: {})
    monkeypatch.setattr(ip_camera, "validate_rtsp_media",
                        lambda url, *a, **k: ("_channel=0_stream=0" in url, "video"))
    monkeypatch.setattr(ip_camera, "_video_frame_signature", lambda *a, **k: 1 << 100)
    monkeypatch.setattr(ip_camera, "_direct_audio_fields", lambda *a, **k: {})
    monkeypatch.setattr(ip_camera, "probe_dvrip_media",
                        lambda *a, channel=0, subtype=0, **k: SimpleNamespace(
                            ok=(channel == 2 and subtype == 0), codec="h264", detail="video"))
    monkeypatch.setattr(ip_camera, "dvrip_frame_signature", lambda *a, **k: 1 << 100)
    channels = ip_camera._scan_itblue_x3_multilens_rtsp("192.0.2.47", "u", "p")
    assert [(ch.channel, ch.source_name) for ch in channels] == [(1, "Lente PTZ")]


def test_native_fixed_channel_without_decoded_image_is_not_promoted(monkeypatch):
    monkeypatch.setattr(ip_camera, "dvrip_multilens_hints", lambda *a, **k: {})
    monkeypatch.setattr(ip_camera, "validate_rtsp_media", lambda *a, **k: (False, ""))
    monkeypatch.setattr(ip_camera, "probe_dvrip_media",
                        lambda *a, channel=0, subtype=0, **k: SimpleNamespace(
                            ok=(channel == 2 and subtype == 0), codec="h264", detail="video"))
    monkeypatch.setattr(ip_camera, "dvrip_frame_signature", lambda *a, **k: None)
    assert ip_camera._scan_itblue_x3_multilens_rtsp("192.0.2.47", "u", "p") == []


def test_missing_first_lens_does_not_renumber_other_lenses():
    assert ip_camera._x3_logical_channel("xm:1") == 2
    assert ip_camera._x3_logical_channel("xm:2") == 3
    assert ip_camera._x3_logical_channel("onvif:5") == 3
    assert ip_camera._x3_logical_channel("xm:3") == 0


def test_route_change_restarts_only_validated_existing_channel(tmp_path):
    db = Database(tmp_path / "test.db")
    did = db.upsert_device(Device(site_id=db.list_sites()[0]["id"], name="X3", ip="192.0.2.47"))
    def channel(number, url, available=True):
        return SimpleNamespace(channel=number, name=f"Lente {number}", source_name=f"Lente {number}",
                               rtsp_url=url, main_rtsp_url=url, sub_rtsp_url="", available=available,
                               detail="verified", route_kind="direct", channel_kind="ip")
    db.replace_recorder_channels(did, [channel(1, "rtsp://cam/0"), channel(2, "rtsp://cam/1")])
    old = db.list_recorder_channels(did)
    db.replace_recorder_channels(did, [channel(1, "rtsp://cam/0"), channel(2, "dvrip://cam/?channel=1")])
    new = db.list_recorder_channels(did)
    assert changed_channel_routes(old, new) == {old[1]["id"]}
    assert old[1]["id"] == new[1]["id"]
    db.close()

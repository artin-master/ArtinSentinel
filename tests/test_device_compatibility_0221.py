from pathlib import Path

import artin_sentinel.ip_camera as ip_camera
import artin_sentinel.recorder as recorder
import artin_sentinel.xm_dvrip as xm
from artin_sentinel.native_protocols import (
    NativeHttpProbeResult,
    HikvisionStreamingInventory,
    probe_hikvision_isapi_streaming_channels,
)


def test_hikvision_streaming_inventory_parses_advertised_ids(monkeypatch):
    xml = b'''<?xml version="1.0"?>
    <StreamingChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema">
      <StreamingChannel><id>101</id></StreamingChannel>
      <StreamingChannel><id>102</id></StreamingChannel>
      <StreamingChannel><id>501</id></StreamingChannel>
      <StreamingChannel><id>502</id></StreamingChannel>
    </StreamingChannelList>'''
    monkeypatch.setattr(
        "artin_sentinel.native_protocols._hikvision_isapi_get",
        lambda *a, **k: (200, xml, "http://device/ISAPI/Streaming/channels", "OK"),
    )
    result = probe_hikvision_isapi_streaming_channels("192.0.2.10", "u", "p")
    assert result.authenticated is True
    assert result.stream_ids == (101, 102, 501, 502)
    assert result.physical_channels == (1, 5)


def test_hikvision_scan_prefers_isapi_advertised_physical_channels(monkeypatch):
    monkeypatch.setattr(
        recorder, "probe_hikvision_isapi_device_info",
        lambda *a, **k: NativeHttpProbeResult(ok=True, authenticated=True, status_code=200, manufacturer="Hikvision", model="DVR"),
    )
    monkeypatch.setattr(
        recorder, "probe_hikvision_isapi_streaming_channels",
        lambda *a, **k: HikvisionStreamingInventory(ok=True, authenticated=True, status_code=200, stream_ids=(501, 502), physical_channels=(5,), detail="1 canal"),
    )
    calls = []
    def fake_probe(url, username, password, *a, **k):
        calls.append(url)
        ok = url.endswith("/501")
        return recorder.RtspProbeReport(ok=ok, status_code=200 if ok else 404, detail="OK" if ok else "no")
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", fake_probe)
    monkeypatch.setattr(recorder, "_audio_fields_for_urls", lambda *a, **k: {})
    channels = recorder.scan_hikvision_channels("192.0.2.10", "u", "p", max_channels=18)
    assert [c.channel for c in channels] == [5]
    assert any(url.endswith("/501") for url in calls)
    assert not any("/101" in url for url in calls)


def test_dvrip_multilens_hints_only_returns_sanitized_counts(monkeypatch):
    class FakeSession:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def get_config(self, name):
            if name == "Camera":
                return {"ChannelNum": 3, "Secret": "must-not-escape"}
            if name == "Simplify.Encode":
                return {"Encode": [{}, {}, {}]}
            raise xm.DvripError("unsupported")
    monkeypatch.setattr(xm, "DvripSession", FakeSession)
    result = xm.dvrip_multilens_hints("192.0.2.20", "u", "secret")
    assert result["channel_count_hint"] == 3
    assert result["config_objects"] == ("Camera", "Simplify.Encode")
    assert "Secret" not in repr(result)
    assert "must-not-escape" not in repr(result)


def test_multilens_paired_capture_rejects_same_encoder(monkeypatch):
    values = {"candidate": 0xAAAA, "accepted": 0xAAAA, "other": 0x0F0F}
    monkeypatch.setattr(ip_camera, "_video_frame_signature", lambda url, *a, **k: values[url])
    monkeypatch.setattr(ip_camera.time, "sleep", lambda *_: None)
    assert ip_camera._paired_visual_alias("candidate", ["accepted"], "u", "p") is True
    assert ip_camera._paired_visual_alias("other", ["accepted"], "u", "p", threshold=4) is False


def test_hikvision_diagnostic_action_is_exposed_in_device_menu():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "Diagnóstico Hikvision (somente leitura)" in source
    assert "hikvision_compatibility_report" in source

from pathlib import Path
from types import SimpleNamespace

import artin_sentinel.native_protocols as native
import artin_sentinel.recorder as recorder
from artin_sentinel import __version__
from artin_akdb import CORE_REVISION, record_by_legacy_key


def test_version_and_shared_akdb_revision_0222():
    assert __version__ == "0.2.93"
    assert CORE_REVISION >= 5
    row = record_by_legacy_key("hikvision-ds-7216hghi-f1")
    assert row is not None
    assert row.canonical_type == "dvr"
    assert "deviceType=IPC-unreliable-for-classification" in row.negative_knowledge
    assert row.validation_status == "field-validated"


def test_hikvision_video_inputs_parser(monkeypatch):
    xml = b'''<?xml version="1.0"?><VideoInputChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema">
    <VideoInputChannel><id>1</id><inputPort>1</inputPort><videoInputEnabled>false</videoInputEnabled><name>Camera 01</name><videoFormat>PAL</videoFormat><resDesc>NO VIDEO</resDesc></VideoInputChannel>
    <VideoInputChannel><id>2</id><inputPort>2</inputPort><videoInputEnabled>true</videoInputEnabled><name>Camera 02</name><videoFormat>PAL</videoFormat><resDesc>1080P</resDesc></VideoInputChannel>
    </VideoInputChannelList>'''
    monkeypatch.setattr(native, "_hikvision_isapi_get", lambda *a, **k: (200, xml, "http://device", "OK"))
    inv = native.probe_hikvision_isapi_video_inputs("192.0.2.1", "admin", "pw")
    assert inv.authenticated and inv.ok
    assert len(inv.inputs) == 2
    assert inv.inputs[0].enabled is False
    assert inv.inputs[0].resolution_description == "NO VIDEO"
    assert inv.inputs[1].enabled is True
    assert "1 com sinal" in inv.detail


def test_hikvision_proxy_status_parser(monkeypatch):
    xml = b'''<?xml version="1.0"?><InputProxyChannelStatusList xmlns="http://www.hikvision.com/ver20/XMLSchema">
      <InputProxyChannelStatus><id>17</id><sourceInputPortDescriptor><proxyProtocol>ONVIF</proxyProtocol><ipAddress>192.168.15.3</ipAddress><managePortNo>80</managePortNo><srcInputPort>1</srcInputPort></sourceInputPortDescriptor><online>false</online><chanDetectResult>unknownError</chanDetectResult></InputProxyChannelStatus>
    </InputProxyChannelStatusList>'''
    monkeypatch.setattr(native, "_hikvision_isapi_get", lambda *a, **k: (200, xml, "http://device", "OK"))
    inv = native.probe_hikvision_input_proxy_status("192.0.2.1", "admin", "pw")
    assert inv.ok and len(inv.channels) == 1
    ch = inv.channels[0]
    assert ch.channel_id == 17
    assert ch.protocol == "ONVIF"
    assert ch.ip_address == "192.168.15.3"
    assert ch.online is False
    assert ch.detect_result == "unknownError"


def test_hikvision_scan_keeps_no_video_inventory_without_blind_rtsp(monkeypatch):
    monkeypatch.setattr(recorder, "probe_hikvision_isapi_device_info", lambda *a, **k: SimpleNamespace(
        authenticated=True, status_code=200, manufacturer="", model="DS-7216HGHI-F1", detail="OK"
    ))
    monkeypatch.setattr(recorder, "probe_hikvision_isapi_streaming_channels", lambda *a, **k: SimpleNamespace(
        stream_ids=(), physical_channels=(), detail="sem IDs"
    ))
    monkeypatch.setattr(recorder, "probe_hikvision_isapi_video_inputs", lambda *a, **k: SimpleNamespace(
        inputs=(SimpleNamespace(channel_id=1, input_port=1, enabled=False, name="Camera 01", video_format="PAL", resolution_description="NO VIDEO"),),
        detail="1 entrada; 0 com sinal"
    ))
    monkeypatch.setattr(recorder, "probe_hikvision_input_proxy_status", lambda *a, **k: SimpleNamespace(
        channels=(SimpleNamespace(channel_id=17, protocol="ONVIF", ip_address="192.168.15.3", port=80, source_input_port=1, online=False, detect_result="unknownError"),),
        detail="1 canal IP; 0 online"
    ))
    calls = []
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", lambda *a, **k: calls.append(a) or recorder.RtspProbeReport(False, 404, "no"))
    rows = recorder.scan_hikvision_channels("192.0.2.10", "admin", "pw", max_channels=18)
    assert [row.channel for row in rows] == [1, 17]
    assert all(not row.available for row in rows)
    assert rows[0].channel_kind == "analog"
    assert "sem sinal" in rows[0].detail
    assert rows[1].channel_kind == "ip"
    assert "offline" in rows[1].detail
    assert calls == []


def test_fullscreen_path_preserves_live_sessions_and_mosaic_scaling_is_lightweight():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    block = source[source.index("    def focus_video_tile"):source.index("    def _enter_primary_fullscreen")]
    assert "rebuild_video_grid(1)" not in block
    assert "stop_all_live_streams" not in block
    assert "candidate.hide()" in block
    assert "_restore_video_grid_geometry" in source
    assert "Qt.FastTransformation" in source
    assert "self.live_poll_timer.setInterval(100)" in source
    assert "if count <= 9:\n            return 8" in source


def test_installer_reports_real_0222_version():
    install = Path("install.sh").read_text(encoding="utf-8")
    assert 'NEW_VERSION="0.2.93"' in install
    assert 'Artin Sentinel $NEW_VERSION instalado/atualizado.' in install
    assert 'Artin Sentinel 0.2.19 instalado/atualizado.' not in install

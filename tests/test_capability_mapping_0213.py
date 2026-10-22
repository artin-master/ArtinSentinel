from pathlib import Path

from artin_sentinel import __version__
from artin_sentinel.akdb import best_profile, capability_map, recorder_scan_limit
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.ip_camera import direct_camera_provider_hint
from artin_sentinel.native_protocols import plans_for
from artin_sentinel.providers import HikvisionProvider, IntelbrasProvider


def test_release_is_0213(release_version):
    assert __version__ == release_version


def test_intelbras_vipc_1230_d_g2_profile_is_specific():
    match = best_profile(
        text="Intelbras VIPC 1230 D G2",
        ports=[80, 554],
        manufacturer="Intelbras",
    )
    assert match is not None
    score, profile = match
    assert score >= 90
    assert profile.key == "intelbras-vipc-1230-d-g2"
    caps = capability_map(profile_key=profile.key)
    assert caps["stream_count"] == 2
    assert caps["onvif_profiles"] == ["S", "T"]
    assert caps["audio"]["mode"] == "none"
    assert caps["ptz"]["mode"] == "none"
    assert caps["rtsp_main"] == "/cam/realmonitor?channel=1&subtype=0"
    assert caps["rtsp_sub"] == "/cam/realmonitor?channel=1&subtype=1"


def test_vipc_manual_identity_routes_to_intelbras_probe():
    assert direct_camera_provider_hint("generic-onvif", "Intelbras", "VIPC 1230 D G2", "Camera") == "intelbras"
    dev = Device(site_id=1, name="VIPC", ip="192.0.2.15", kind=DeviceKind.CAMERA, manufacturer="Intelbras", model="VIPC 1230 D G2")
    assert IntelbrasProvider().score(dev) >= 110


def test_hikvision_ds7216_profile_and_channel_limit():
    match = best_profile(
        text="Hikvision DS-7216HGHI-F1 Turbo HD DVR",
        ports=[80, 554, 8000],
        manufacturer="Hikvision",
    )
    assert match is not None
    score, profile = match
    assert score >= 92
    assert profile.key == "hikvision-ds-7216hghi-f1"
    caps = capability_map(profile_key=profile.key)
    assert caps["max_analog_channels"] == 16
    assert caps["max_ip_channels"] == 2
    assert caps["max_total_channels"] == 18
    assert caps["ptz"]["mode"] == "recorder-mediated"
    assert caps["ptz"]["direct_control"] is False
    assert recorder_scan_limit(profile_key=profile.key) == 18


def test_hikvision_exact_model_scores_above_generic():
    dev = Device(site_id=1, name="DVR", ip="192.0.2.20", kind=DeviceKind.XVR, manufacturer="Hikvision", model="DS-7216HGHI-F1")
    assert HikvisionProvider().score(dev) >= 115


def test_native_protocol_plans_are_read_only():
    hik = plans_for("hikvision", ["hikvision-isapi-readonly-candidate"])
    assert hik and hik[0].read_only is True
    assert "/ISAPI/System/deviceInfo" in hik[0].endpoints
    intel = plans_for("intelbras", ["intelbras-cgi-readonly-candidate"])
    assert intel and intel[0].read_only is True
    assert "action=getSystemInfo" in intel[0].endpoints[0]


def test_vms_devices_and_ptz_ui_are_present():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "EQUIPAMENTOS CADASTRADOS NO SITE" in text
    assert "DETALHES DO EQUIPAMENTO" in text
    assert "Filtrar por nome, IP, fabricante ou modelo" in text
    assert "Abrir no Live View" in text
    assert "PtzPadButton" in text
    assert "PTZ direto •" in text
    assert "recorder_scan_limit" in text

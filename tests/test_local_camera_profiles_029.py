from pathlib import Path

from artin_sentinel.akdb import PROFILES
from artin_sentinel.ip_camera import _candidate_pairs, direct_camera_provider_hint


def test_aitek_sigma_h2_profile_is_prioritized_with_documented_local_paths():
    pairs = _candidate_pairs("192.0.2.21", "aitek")
    label, main, sub = pairs[0]
    assert label == "Aitek SIGMA H2-52PGX"
    assert main == "rtsp://192.0.2.21:554/live/0/MAIN"
    assert sub == "rtsp://192.0.2.21:554/live/0/SUB"


def test_h2_platform_or_sigma_model_guides_aitek_read_only_probe():
    assert direct_camera_provider_hint("generic-onvif", "", "H2-52PGX", "IPC") == "aitek"
    assert direct_camera_provider_hint("generic-onvif", "", "SIGMA-SEG6050BP", "IPC") == "aitek"


def test_akdb_contains_field_validated_aitek_sigma_profile():
    profile = next(p for p in PROFILES if p.key == "aitek-sigma-seg6050bp")
    assert profile.manufacturer == "Aitek"
    assert profile.family == "SIGMA"
    assert profile.rtsp_main == "/live/0/MAIN"
    assert profile.rtsp_sub == "/live/0/SUB"
    assert profile.validation == "field-validated"
    assert "platform-h2-52pgx" in profile.compatible_with


def test_configuration_exposes_web_interface_action_without_embedding_credentials():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'QPushButton("Abrir Web")' in text
    assert 'Abrir interface Web' in text
    assert 'QDesktopServices.openUrl(QUrl(url))' in text
    # Navigation must use the discovered web_url, never construct user:password@ URLs.
    assert 'device["web_url"]' in text

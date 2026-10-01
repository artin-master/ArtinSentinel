from pathlib import Path
from types import SimpleNamespace

from artin_sentinel.akdb import best_profile, ptz_capability
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.ip_camera import _candidate_pairs, direct_camera_provider_hint
from artin_sentinel.providers import ITBlueProvider
import artin_sentinel.ptz as ptz


def test_x3_we2q_akdb_profile_is_specific_and_conservative():
    match = best_profile(
        text="IT-Blue X3-WE2Q V5.02.R02.000A06CD XM535D1",
        ports=[80, 554, 34567],
        manufacturer="IT-Blue",
    )
    assert match is not None
    score, profile = match
    assert profile.key == "it-blue-x3-we2q"
    assert score >= 85
    assert profile.audio_mode == "bidirectional"
    assert profile.lens_count == 3
    assert profile.ptz_mode == "dvrip-confirmed"
    assert "motion-tracking" in profile.features



def test_generic_itblue_does_not_inherit_x3_profile_from_port_only():
    match = best_profile(text="IT-Blue Web Viewer", ports=[80, 554, 34567], manufacturer="IT-Blue")
    assert match is not None
    assert match[1].key == "it-blue-camera"

def test_x3_we2q_routes_to_itblue_provider_hint():
    assert direct_camera_provider_hint("generic", model="X3-WE2Q") == "it-blue"
    assert direct_camera_provider_hint("generic", model="XM535D1_X3-WE2Q") == "it-blue"
    dev = Device(site_id=1, name="Speed Dome", ip="192.168.15.47", kind=DeviceKind.CAMERA, model="X3-WE2Q")
    assert ITBlueProvider().score(dev) >= 95


def test_itblue_x3_candidates_prioritize_channel_zero_and_onvif_aliases():
    pairs = _candidate_pairs("192.168.15.47", "it-blue")
    labels = [row[0] for row in pairs]
    assert labels[0] == "IT-Blue X3-WE2Q XM ch0"
    assert "channel=0_stream=0.sdp?real_stream" in pairs[0][1]
    assert "channel=0_stream=1.sdp?real_stream" in pairs[0][2]
    assert any(main.endswith("/onvif1") and sub.endswith("/onvif2") for _, main, sub in pairs)


def test_ptz_capability_does_not_project_x3_onto_all_itblue():
    specific = ptz_capability(profile_key="it-blue-x3-we2q")
    generic = ptz_capability(provider="it-blue")
    assert specific["mode"] == "dvrip-confirmed"
    assert specific["lens_count"] == 3
    assert generic["mode"] == "unknown"


def test_onvif_ptz_context_and_bounded_move(monkeypatch):
    calls = []

    def fake_post(url, body, username, password, timeout=4.0):
        text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
        calls.append((url, text))
        if "GetCapabilities" in text:
            return '''<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><GetCapabilitiesResponse><Capabilities><Media><XAddr>http://cam/onvif/media</XAddr></Media><PTZ><XAddr>http://cam/onvif/ptz</XAddr></PTZ></Capabilities></GetCapabilitiesResponse></s:Body></s:Envelope>'''
        if "GetProfiles" in text:
            return '''<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><GetProfilesResponse><Profiles token="profile_1"><Name>Main</Name><PTZConfiguration token="ptz1"/></Profiles></GetProfilesResponse></s:Body></s:Envelope>'''
        return '<ok/>'

    monkeypatch.setattr(ptz, "_post", fake_post)
    monkeypatch.setattr(ptz, "_device_service_candidates", lambda ip, url: [url or "http://cam/onvif/device_service"])
    monkeypatch.setattr(ptz, "sleep", lambda seconds: None)
    result = ptz.pulse_move("192.168.15.47", "user", "pass", "http://cam/onvif/device_service", "left", speed=0.5)
    assert result == "PTZ ONVIF: left"
    joined = "\n".join(text for _, text in calls)
    assert "ContinuousMove" in joined
    assert 'PanTilt x="-0.500" y="0.000"' in joined
    assert "<tptz:Timeout>" in joined
    assert "<tptz:Stop" in joined


def test_live_ui_contains_ptz_controls():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "PTZ / SPEED DOME" in text
    assert "move_selected_ptz" in text
    assert "stop_selected_ptz" in text
    assert "Velocidade do movimento PTZ" in text

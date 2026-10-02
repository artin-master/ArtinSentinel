from pathlib import Path
import json

from artin_sentinel import __version__
from artin_sentinel.akdb import reconcile_operational_profile_key
from artin_sentinel.intelbras_http import post_audio_transport_info
from artin_sentinel.live import _network_failure_reason
from artin_sentinel.talkback import _digest_challenge_params, _digest_authorization


def test_release_0237():
    assert __version__ == "0.2.93"


def test_digest_parser_and_authorization_do_not_include_password():
    scheme, params = _digest_challenge_params(
        'Digest realm="Device", nonce="abc123", qop="auth", opaque="opaque", algorithm=MD5'
    )
    assert scheme == "Digest"
    header = _digest_authorization(
        params, "admin", "super-secret", "POST",
        "/cgi-bin/audio.cgi?action=postAudio&httptype=singlepart&channel=1",
        cnonce="0102030405060708",
    )
    assert header.startswith("Digest ")
    assert 'username="admin"' in header
    assert "super-secret" not in header
    assert "qop=auth" in header


def test_network_failure_classifier_distinguishes_routing_failures():
    assert _network_failure_reason("Connection failed: No route to host") == "sem rota até o host"
    assert _network_failure_reason("Network is unreachable") == "rede inacessível"
    assert _network_failure_reason("Destination Host Unreachable") == "host inacessível"
    assert _network_failure_reason("401 Unauthorized") == ""
    assert _network_failure_reason("Connection refused") == ""


def _device(provider="intelbras-mibo", profile="intelbras-imx-c"):
    return {
        "name": "iMX C",
        "model": "iMX C",
        "detected_name": "MiboCam",
        "detected_model": "iMX C",
        "manufacturer": "Intelbras",
        "detected_manufacturer": "Intelbras",
        "provider": provider,
        "metadata_json": json.dumps({
            "akdb_profile": profile,
            "intelbras_http_api": {
                "supported": True,
                "reachable": True,
                "authenticated": True,
                "base_url": "http://192.168.15.253",
                "api_version": "2.32",
                "audio_inputs": 1,
                "audio_outputs": 1,
                "post_audio_candidate": True,
            },
        }),
    }


def test_positive_http_probe_exposes_transport_candidate():
    device = _device()
    metadata = json.loads(device["metadata_json"])
    info = post_audio_transport_info(metadata)
    assert info["ready"] is True
    assert info["base_url"] == "http://192.168.15.253"
    assert info["audio_channel"] == 1
    assert info["audio_outputs"] == 1


def test_postaudio_transport_stays_disabled_without_concrete_audio_output_evidence():
    device = _device()
    metadata = json.loads(device["metadata_json"])
    metadata["intelbras_http_api"]["audio_outputs"] = 0
    metadata["intelbras_http_api"]["post_audio_candidate"] = False
    info = post_audio_transport_info(metadata)
    assert info["ready"] is False
    assert info["audio_channel"] == 0


def test_imx_strong_model_evidence_repairs_stale_mhdx_profile():
    key = reconcile_operational_profile_key(
        profile_key="intelbras-mhdx", provider="intelbras",
        identity_text="Intelbras MiboCam iMX C",
    )
    assert key == "intelbras-imx-c"


def test_live_source_short_circuits_profile_fallback_on_network_failure():
    source = Path("artin_sentinel/live.py").read_text(encoding="utf-8")
    assert "network_problem = bool((not got) and self._network_failure.is_set())" in source
    assert "if not got and not network_problem and self.transport_fallback" in source
    assert "if not got and not network_problem and self.fallback_url" in source
    assert "schedule = (3.0, 8.0, 15.0, 30.0)" in source
    assert "Host temporariamente inacessível" in source


def test_app_routes_intelbras_http_talkback_separately_from_dvrip():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert '"intelbras-http-postaudio-experimental"' in source
    assert "IntelbrasHttpTalkbackSession(" in source
    assert "Intelbras HTTP postAudio/G.711A" in source


def test_http_session_uses_official_postaudio_and_g711a():
    source = Path("artin_sentinel/talkback.py").read_text(encoding="utf-8")
    assert "POST_AUDIO_PATH.format" in source
    assert "Content-Type', 'Audio/G.711A'" in source
    assert "'-ar', '8000'" in source
    assert "'-c:a', 'pcm_alaw'" in source
    assert "HTTP 6/6" in source

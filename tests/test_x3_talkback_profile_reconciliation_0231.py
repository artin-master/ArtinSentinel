from pathlib import Path

from artin_sentinel import __version__
from artin_sentinel.akdb import audio_capability, reconcile_operational_profile_key


def test_release_version_0231():
    assert __version__ == "0.2.92"


def test_stale_generic_itblue_speeddome_is_reconciled_to_field_x3_profile():
    key = reconcile_operational_profile_key(
        profile_key="it-blue-camera",
        provider="it-blue",
        identity_text="SpeedDome Ball It-blue IT-Blue",
    )
    assert key == "it-blue-x3-we2q"
    audio = audio_capability(profile_key=key)
    assert audio["talkback_protocol"] == "xm-dvrip-g711a-experimental"
    assert audio["talkback_scope"] == "primary"


def test_generic_itblue_without_x3_field_evidence_is_not_promoted():
    key = reconcile_operational_profile_key(
        profile_key="it-blue-camera",
        provider="it-blue",
        identity_text="IT-Blue Web Viewer camera",
    )
    assert key == "it-blue-camera"


def test_non_itblue_speeddome_is_not_promoted():
    key = reconcile_operational_profile_key(
        profile_key="",
        provider="generic",
        identity_text="Speed Dome Ball camera",
    )
    assert key == ""


def test_live_audio_path_uses_operational_profile_reconciliation_before_capability_lookup():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    idx_reconcile = source.index("profile_key = reconcile_operational_profile_key(")
    idx_capability = source.index("known = audio_capability(provider=provider_name, profile_key=profile_key)")
    assert idx_reconcile < idx_capability

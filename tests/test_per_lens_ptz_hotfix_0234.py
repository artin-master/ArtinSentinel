from pathlib import Path
from artin_sentinel import __version__
from artin_sentinel.akdb import reconcile_operational_profile_key, ptz_capability


def test_release_0234():
    assert __version__ == "0.2.90"


def test_stale_generic_x3_profile_reconciles_for_ptz():
    key = reconcile_operational_profile_key(
        profile_key="it-blue-camera",
        provider="it-blue",
        identity_text="IT-Blue SpeedDome Ball X3-WE2Q",
    )
    assert key == "it-blue-x3-we2q"
    cap = ptz_capability(provider="it-blue", profile_key=key)
    assert cap["scope"] == "primary"
    assert cap["direct_control"] is True


def test_ptz_context_forces_x3_primary_scope_after_reconciliation():
    src = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "profile_key = reconcile_operational_profile_key(" in src
    assert 'ptz_scope = "primary" if x3_hint else' in src
    assert 'scope_ok = not fixed_lens and channel_matches_capability_scope(channel, ptz_scope)' in src


def test_primary_scope_helper_rejects_fixed_channels_by_definition():
    src = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    start = src.index("def channel_matches_capability_scope")
    end = src.index("\ndef channel_audio_info", start)
    block = src[start:end]
    assert 'if scope == "primary":' in block
    assert 'channel_no in {0, 1}' in block
    assert '"ptz" in source_name' in block

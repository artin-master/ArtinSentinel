from pathlib import Path

from artin_sentinel import __version__
from artin_sentinel.akdb import (
    audio_capability,
    best_profile,
    reconcile_operational_profile_key,
)
from artin_akdb import CORE_REVISION, record_by_legacy_key


def test_release_0235_and_core_revision():
    assert __version__ == "0.2.90"
    assert CORE_REVISION >= 12


def test_imx_c_has_specific_core_and_sentinel_profile():
    core = record_by_legacy_key("intelbras-imx-c")
    assert core is not None
    assert core.model == "iMX C"
    assert "listen-audio-field-validated" in core.capabilities
    assert "bidirectional-audio-hardware" in core.capabilities
    assert "intelbras-1-candidate" in core.protocols

    matched = best_profile(text="Intelbras iMX C", manufacturer="Intelbras")
    assert matched is not None
    _score, profile = matched
    assert profile.key == "intelbras-imx-c"
    assert profile.audio_codecs == ("AAC",)


def test_stale_generic_mibo_reconciles_to_imx_c_but_mic_stays_pending():
    key = reconcile_operational_profile_key(
        profile_key="intelbras-mibo", provider="intelbras-mibo",
        identity_text="Intelbras MiboCam iMX C",
    )
    assert key == "intelbras-imx-c"
    audio = audio_capability(profile_key=key)
    assert audio["mode"] == "bidirectional"
    assert audio["talkback_protocol"] == "intelbras-1-candidate"
    assert audio["talkback_validation"] == "candidate"

    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert '"xm-dvrip-g711a-experimental"' in app
    assert '"intelbras-http-postaudio-experimental"' in app
    assert 'self.audio_talkback_badge.setText("MIC PEND")' in app


def test_dvrip_secondary_socket_can_attach_existing_session_without_login():
    src = Path("artin_sentinel/xm_dvrip.py").read_text(encoding="utf-8")
    assert "def attach_authenticated_session" in src
    assert "def sync_sequence_from" in src
    assert "self.session = int(session)" in src
    assert "self.sequence = int(sequence)" in src


def test_talkback_topology_is_control_plus_attached_talk_socket():
    src = Path("artin_sentinel/talkback.py").read_text(encoding="utf-8")
    assert "talk.attach_authenticated_session(control.session, control.sequence)" in src
    assert "talk.talk_claim()" in src
    assert "control.sync_sequence_from(talk)" in src
    assert "control.talk_start_no_reply()" in src
    assert "talk.send_talk_audio(chunk)" in src
    assert "control.talk_stop_no_reply()" in src
    assert "DVRIP 6/6" in src

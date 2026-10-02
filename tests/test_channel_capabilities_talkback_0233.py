from pathlib import Path
from types import SimpleNamespace

import artin_sentinel.talkback as talkback
from artin_sentinel import __version__
from artin_sentinel.akdb import audio_capability, ptz_capability
from artin_akdb import CORE_REVISION, record_by_legacy_key


def test_release_0233_and_akdb_revision():
    assert __version__ == "0.2.92"
    assert CORE_REVISION >= 11
    x3 = record_by_legacy_key("it-blue-x3-we2q")
    assert x3 is not None
    assert "fixed-lenses-field-detected" in x3.capabilities
    assert "xm-dvrip-fixed-lenses-not-homologated" in x3.negative_knowledge
    mibo = record_by_legacy_key("intelbras-mibo")
    assert mibo is not None
    assert "listen-audio-field-validated" in mibo.capabilities
    assert "talkback-local-transport-not-homologated" in mibo.negative_knowledge


def test_x3_ptz_and_talkback_are_primary_lens_scoped():
    ptz = ptz_capability(profile_key="it-blue-x3-we2q")
    audio = audio_capability(profile_key="it-blue-x3-we2q")
    assert ptz["mode"] == "dvrip-confirmed"
    assert ptz["scope"] == "primary"
    assert audio["talkback_scope"] == "primary"


def test_live_view_applies_channel_scope_to_ptz_and_mic_pending_ui():
    src = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "def channel_matches_capability_scope" in src
    assert "scope_ok = not fixed_lens and channel_matches_capability_scope(channel, ptz_scope)" in src
    assert 'channel = self.db.get_recorder_channel(int(tile.source.get("channel_id", 0)))' in src
    assert 'self.audio_talkback_badge.setText("MIC PEND")' in src
    assert "retorno local ainda não homologado" in src


def test_mibo_keeps_bidirectional_candidate_without_exposing_unvalidated_transport():
    audio = audio_capability(profile_key="intelbras-mibo")
    assert audio["mode"] == "bidirectional"
    assert audio["talkback_protocol"] == "unvalidated"
    assert audio["talkback_validation"] == "unvalidated"


def test_xm_talkback_uses_shared_session_secondary_talk_socket_and_reports_stages(monkeypatch):
    events = []
    instances = []

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.session = 0
            self.sequence = 0
            self.is_control = len(instances) == 0
            instances.append(self)
        def __enter__(self):
            self.session = 0x1B
            self.sequence = 1
            events.append("login-control")
            return self
        def __exit__(self, exc_type, exc, tb):
            events.append("close-control")
        def connect(self):
            events.append("connect-talk")
        def attach_authenticated_session(self, session, sequence):
            self.connect()
            self.session = session
            self.sequence = sequence
            events.append(("attach", session, sequence))
        def sync_sequence_from(self, other):
            self.sequence = other.sequence
            events.append(("sync", self.sequence))
        def talk_claim(self):
            events.append(("claim-talk", self.sequence))
            self.sequence += 1
            return {"Ret": 100}
        def talk_start_no_reply(self):
            events.append(("start-control", self.sequence))
            self.sequence += 1
        def send_talk_audio(self, chunk):
            events.append(("audio-talk", len(chunk)))
        def drain_pending(self):
            events.append("drain-talk")
            return 0
        def talk_stop_no_reply(self):
            events.append(("stop-control", self.sequence))
            self.sequence += 1
        def close(self):
            events.append("close-talk")

    class Stdout:
        def __init__(self):
            self.calls = 0
        def read(self, n):
            self.calls += 1
            return b"\xd5" * 320 if self.calls == 1 else b""

    class FakeProc:
        def __init__(self, cmd):
            self.cmd = cmd
            self.stdout = Stdout()
            self.stderr = SimpleNamespace(read=lambda n=-1: b"")
        def poll(self): return 0
        def terminate(self): pass
        def wait(self, timeout=None): return 0
        def kill(self): pass

    monkeypatch.setattr(talkback, "DvripSession", FakeSession)
    monkeypatch.setattr(talkback.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(talkback, "ffmpeg_microphone_inputs", lambda: frozenset({"pulse"}))
    monkeypatch.setattr(talkback.subprocess, "Popen", lambda cmd, **kwargs: FakeProc(cmd))

    sess = talkback.XmDvripTalkbackSession(
        "192.0.2.47", "admin", "pw", microphone_backend="pulse",
        microphone_source="default", microphone_label="Webcam C270 Mono", gain_db=6,
    )
    sess._run()

    assert len(instances) == 2
    assert ("attach", 0x1B, 1) in events
    assert ("claim-talk", 1) in events
    assert ("start-control", 2) in events
    assert ("audio-talk", 320) in events
    assert ("stop-control", 3) in events
    diagnostics = "\n".join(sess.drain_diagnostics())
    for step in range(1, 7):
        assert f"DVRIP {step}/6" in diagnostics


def test_talkback_stop_does_not_close_dvrip_session_from_gui_thread():
    src = Path("artin_sentinel/talkback.py").read_text(encoding="utf-8")
    start = src.index("    def stop(self) -> None:", src.index("class XmDvripTalkbackSession"))
    end = src.index("    def _capture_commands", start)
    block = src[start:end]
    assert "_terminate_process_nonblocking" in block
    assert ".close()" not in block
    assert ".join(" not in block


def test_mic_button_is_click_to_toggle_not_mouse_hold():
    src = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "self.talkback_btn.setCheckable(True)" in src
    assert "self.talkback_btn.clicked.connect(self.toggle_selected_talkback)" in src
    assert "self.talkback_btn.pressed.connect" not in src
    assert "self.talkback_btn.released.connect" not in src
    assert 'self.talkback_btn.setText("PARAR")' in src
    assert 'self.talkback_btn.setText("MIC")' in src
    assert 'self.talkback_btn.setText("MIC INDISP.")' in src

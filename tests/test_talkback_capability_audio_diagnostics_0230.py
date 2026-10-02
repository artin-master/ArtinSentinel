from pathlib import Path

import artin_sentinel.talkback as talkback
from artin_sentinel.akdb import audio_capability


def test_itblue_x3_talkback_capability_is_primary_and_experimental():
    audio = audio_capability(profile_key="it-blue-x3-we2q")
    assert audio["mode"] == "bidirectional"
    assert audio["talkback_protocol"] == "xm-dvrip-g711a-experimental"
    assert audio["talkback_scope"] == "primary"
    assert audio["talkback_validation"] == "experimental"


def test_unvalidated_mibo_does_not_become_operational_talkback():
    audio = audio_capability(profile_key="intelbras-mibo")
    assert audio["mode"] == "bidirectional"
    assert audio["talkback_protocol"] == "unvalidated"
    assert audio["talkback_validation"] == "unvalidated"


def test_ui_exposes_experimental_mic_from_known_capability_without_downgrading_to_listen_only():
    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'known_mode == "bidirectional"' in app
    assert 'scope_ok = channel_matches_capability_scope(channel, talkback_scope)' in app
    assert 'channel_no in {0, 1}' in app
    assert 'self.audio_talkback_badge.setText("MIC EXP"' in app
    assert 'self.microphone_row.setVisible(can_talk)' in app
    assert 'MIC {validation_text}' in app


def test_microphone_level_probe_parses_ffmpeg_volumedetect(monkeypatch):
    monkeypatch.setattr(talkback.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)

    class Completed:
        returncode = 0
        stderr = "[Parsed_volumedetect_0] mean_volume: -28.4 dB\n[Parsed_volumedetect_0] max_volume: -8.2 dB\n"

    seen = {}
    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return Completed()

    monkeypatch.setattr(talkback.subprocess, "run", fake_run)
    mic = talkback.MicrophoneInput(
        "pulse",
        "alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.mono-fallback",
        "Webcam C270 Mono",
    )
    result = talkback.probe_microphone_level(mic, gain_db=6, duration=1.0)
    assert result.ok is True
    assert result.mean_db == -28.4
    assert result.peak_db == -8.2
    assert "volume=6dB,alimiter=limit=0.95:level=false,volumedetect" in seen["cmd"]
    assert mic.source in seen["cmd"]


def test_microphone_test_runs_in_audio_executor_not_qt_event_loop():
    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "def test_selected_microphone_async" in app
    assert "self.audio_executor.submit(" in app
    assert "probe_microphone_level, microphone" in app
    assert 'self.microphone_test_btn.setText("TEST")' in app

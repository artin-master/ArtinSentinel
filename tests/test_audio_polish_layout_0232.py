from pathlib import Path
from types import SimpleNamespace

import artin_sentinel.live as live
from artin_sentinel import __version__


def test_release_0232():
    assert __version__ == "0.2.90"


def test_pipewire_is_preferred_and_ffplay_is_real_fallback(monkeypatch):
    monkeypatch.setattr(
        live.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"ffplay", "ffmpeg", "pactl"} else None,
    )
    monkeypatch.setattr(live, "ffmpeg_audio_output_devices", lambda: frozenset({"pulse", "alsa"}))
    monkeypatch.setattr(live, "ffmpeg_rtsp_timeout_args", lambda: ())
    sess = live.LiveAudioSession("rtsp://camera/main", volume=75)
    commands = sess._commands("rtsp://camera/main", "tcp")
    assert [name for name, _ in commands] == ["FFmpeg/Pulse-PipeWire", "FFmpeg/ALSA", "ffplay/SDL"]
    ffplay = next(cmd for name, cmd in commands if name == "ffplay/SDL")
    assert "-nostdin" not in ffplay
    pulse = next(cmd for name, cmd in commands if name == "FFmpeg/Pulse-PipeWire")
    assert pulse[-2:] == ["pulse", "default"]


def test_transient_rtsp_errors_are_classified_for_retry():
    assert live._transient_rtsp_error("method OPTIONS failed: 503 (Service Unavailable)")
    assert live._transient_rtsp_error("Server returned 5XX Server Error reply")
    assert not live._transient_rtsp_error("401 Unauthorized")


def test_low_value_ffmpeg_warnings_are_filtered():
    assert live._low_value_ffmpeg_warning("Non-monotonic DTS; previous: 4 current: 3")
    assert live._low_value_ffmpeg_warning("deprecated pixel format used, make sure you did set range correctly")
    assert not live._low_value_ffmpeg_warning("method OPTIONS failed: 503")


def test_current_audio_state_is_distinct_from_history():
    sess = live.LiveAudioSession(
        "rtsp://camera/main", audio_confirmed=True, audio_codec="aac", audio_sample_rate=16000
    )
    sess.detected_codec = "aac"
    sess.detected_sample_rate = 16000
    sess.current_backend = "FFmpeg/Pulse-PipeWire"
    sess.current_state = "active"
    assert "ATIVO" in sess.current_state_text()
    assert "AAC 16000 Hz" in sess.current_state_text()
    assert "FFmpeg/Pulse-PipeWire" in sess.current_state_text()
    sess.had_transient_failure = True
    assert "ATIVO" in sess.current_state_text()


def test_transient_input_failure_stops_backend_fanout(monkeypatch):
    monkeypatch.setattr(live.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffplay"} else None)
    monkeypatch.setattr(live, "ffmpeg_audio_output_devices", lambda: frozenset({"pulse", "alsa"}))
    monkeypatch.setattr(live, "ffmpeg_rtsp_timeout_args", lambda: ())

    calls = []
    class FakeProc:
        returncode = 1
        pid = 999
        def __init__(self, cmd):
            self.cmd = cmd
            self.stderr = SimpleNamespace(read=lambda: b"method OPTIONS failed: 503 (Service Unavailable)\n")
        def poll(self):
            return 1

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return FakeProc(cmd)

    monkeypatch.setattr(live.subprocess, "Popen", fake_popen)
    sess = live.LiveAudioSession("rtsp://camera/main", audio_confirmed=True, audio_codec="aac", audio_sample_rate=16000)
    ok, detail = sess._try_player("rtsp://camera/main", "tcp", codec="aac", sample_rate=16000)
    assert not ok
    assert "503" in detail or "Service Unavailable" in detail
    assert len(calls) == 1
    assert sess.current_state == "retrying"


def test_live_inspector_is_resizable_and_mic_controls_are_wrapped():
    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "inspector.setMinimumWidth(285)" in app
    assert "inspector.setMaximumWidth(460)" in app
    assert 'self.ui_settings.setValue("live/inspector_width", width)' in app
    assert "QGridLayout(self.microphone_row)" in app
    assert "AdjustToMinimumContentsLengthWithIcon" in app
    assert "QSizePolicy.Ignored" in app
    assert 'Estado atual do áudio:' in app


def test_confirmed_audio_fast_path_has_retry_backoff_without_gui_sleep():
    src = Path("artin_sentinel/live.py").read_text(encoding="utf-8")
    assert "for attempt, delay in enumerate((0.0, 0.8, 1.6), start=1)" in src
    assert "self._stop.wait(delay)" in src
    assert "Áudio ocupado no DVR" in src
    assert "_attach_dynamic_volume_async" in src

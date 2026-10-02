import subprocess
import sys
import threading

import artin_sentinel.live as live


def test_live_ffmpeg_without_frames_is_classified_and_reaped(monkeypatch):
    monkeypatch.setattr(live, "FRAME_INACTIVITY_TIMEOUT", 0.05)
    session = live.LiveStreamSession("rtsp://camera/main", "operator", "secret", fps=8, profile_name="Substream")
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, bufsize=0,
    )
    monkeypatch.setattr(session, "_command", lambda *_args: [sys.executable, "-c", "import time; time.sleep(10)"])
    monkeypatch.setattr(live.subprocess, "Popen", lambda *_args, **_kwargs: child)
    try:
        assert session._attempt_profile(session.url, "Substream") is False
        snapshot = session.diagnostics_snapshot()
        assert snapshot["profile"] == "Substream"
        assert snapshot["fps_target"] == 8
        assert snapshot["frame_count"] == 0
        assert snapshot["last_error_class"] == "frame_timeout"
        assert "processo ainda ativo" in snapshot["last_error_origin"]
        assert "FFmpeg permaneceu ativo sem frame" in snapshot["last_reconnect_cause"]
        assert "Watchdog" in " ".join(session.drain_diagnostics())
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_stream_failure_and_backoff_are_scoped_to_one_channel(monkeypatch):
    first = live.LiveStreamSession("rtsp://camera-a/main")
    second = live.LiveStreamSession("rtsp://camera-b/main")
    calls = []
    monkeypatch.setattr(live.LiveStreamSession, "decoder_available", property(lambda _self: True))
    monkeypatch.setattr(first, "_attempt_profile", lambda *_args: calls.append("a") or False)
    monkeypatch.setattr(second, "_attempt_profile", lambda *_args: calls.append("b") or False)

    def stop_after_first_retry(_delay):
        first.stop()
        return True

    monkeypatch.setattr(first._stop, "wait", stop_after_first_retry)
    first._run()
    assert calls == ["a"]
    assert second.attempts == 0
    assert second.current_state == "idle"


def test_closed_tile_session_does_not_schedule_a_retry(monkeypatch):
    session = live.LiveStreamSession("rtsp://camera/main")
    session.stop()
    attempt = []
    monkeypatch.setattr(session, "_attempt_profile", lambda *_args: attempt.append(True) or False)
    session._run()
    assert attempt == []
    assert session.current_state == "stopped"


def test_ffmpeg_stderr_classifier_separates_network_decoder_and_authentication():
    assert live.classify_live_ffmpeg_error("Connection timed out") == ("network", "rede/RTSP")
    assert live.classify_live_ffmpeg_error("Error while decoding MB 0 1") == ("decoder", "decoder/fluxo")
    assert live.classify_live_ffmpeg_error("401 Unauthorized") == ("authentication", "fonte/credencial")

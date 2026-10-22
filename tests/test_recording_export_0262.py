from io import StringIO
from pathlib import Path
from threading import Event

import pytest

from artin_sentinel import recording_export as exp
from artin_sentinel.live import LiveStreamSession


def test_playback_decoder_is_paced_and_stops_at_end():
    session = LiveStreamSession("rtsp://192.0.2.8/cam/playback", playback=True)
    assert ["-readrate", "1"] == session._command(session.url)[session._command(session.url).index("-readrate"):][:2]
    assert "-readrate" not in LiveStreamSession("rtsp://192.0.2.8/live")._command("rtsp://192.0.2.8/live")


def test_playback_speed_sets_input_rate_and_timestamps():
    session = LiveStreamSession("rtsp://192.0.2.8/cam/playback", playback=True, playback_speed=2.0)
    command = session._command(session.url)
    assert command[command.index("-readrate") + 1] == "2"
    assert "setpts=PTS/2" in command[command.index("-vf") + 1]


def test_mp4_export_publishes_completed_file_only(monkeypatch, tmp_path):
    monkeypatch.setattr(exp.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(exp, "ffmpeg_rtsp_timeout_args", lambda: ())
    seen = []

    class FakeProcess:
        stderr = StringIO("")
        stdout = StringIO("out_time=00:00:01.000000\nprogress=end\n")

        def __init__(self, command, **kwargs):
            seen.extend(command)
            Path(command[-1]).write_bytes(b"0" * 2048)

        def wait(self, **kwargs):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(exp.subprocess, "Popen", FakeProcess)
    # Publication unit test; real ffprobe/duration validation has separate media tests.
    monkeypatch.setattr(exp,"validate_export_media",lambda *a:10)
    destination = tmp_path / "clip.mp4"
    updates = []
    assert exp.export_mp4("rtsp://192.0.2.8/cam/playback", "admin", "secret", str(destination), 10,
                          progress=updates.append) == destination
    assert destination.stat().st_size == 2048
    assert "copy" in seen and "aac" in seen and updates[-1] == "Convertido • 100%"
    assert list(tmp_path.glob(".sentinel-export-*")) == []
    with pytest.raises(exp.RecordingExportError, match="já existe"):
        exp.export_mp4("rtsp://192.0.2.8/cam/playback", "admin", "secret", str(destination), 10)


def test_cancel_does_not_publish_file(monkeypatch, tmp_path):
    monkeypatch.setattr(exp.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    cancel = Event()
    cancel.set()
    with pytest.raises(exp.RecordingExportError, match="cancelada"):
        exp.export_mp4("rtsp://192.0.2.8/cam/playback", "u", "p", str(tmp_path / "clip.mp4"), 10, cancel=cancel)
    assert list(tmp_path.iterdir()) == []

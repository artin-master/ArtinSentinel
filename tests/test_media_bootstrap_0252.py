import subprocess

from tools import check_media_runtime as preflight


def test_media_preflight_requires_both_camera_decoders_and_frame(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(exe, *args, **kwargs):
        if "-decoders" in args:
            return subprocess.CompletedProcess([], 0, b" VFS..D h264 camera\n", b"")
        if "demuxer=rtsp" in args:
            return subprocess.CompletedProcess([], 0, b"Demuxer rtsp [RTSP input]", b"")
        return subprocess.CompletedProcess([], 0, bytes(16 * 16 * 3), b"")

    monkeypatch.setattr(preflight, "run", fake_run)
    status = dict(preflight.check_media())
    assert status["decoder h264"]
    assert not status["decoder hevc"]
    assert status["quadro RGB24"]


def test_media_preflight_rejects_broken_frame_and_rtsp(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(exe, *args, **kwargs):
        if "-decoders" in args:
            return subprocess.CompletedProcess([], 0, b" VFS..D h264 camera\n VFS..D hevc camera\n", b"")
        if "demuxer=rtsp" in args:
            return subprocess.CompletedProcess([], 1, b"", b"Unknown demuxer")
        return subprocess.CompletedProcess([], 0, b"incomplete", b"")

    monkeypatch.setattr(preflight, "run", fake_run)
    status = dict(preflight.check_media())
    assert status["decoder h264"] and status["decoder hevc"]
    assert not status["quadro RGB24"]
    assert not status["RTSP ffprobe"]


def test_media_preflight_rejects_missing_executables(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)
    assert all(not ok for _, ok in preflight.check_media())

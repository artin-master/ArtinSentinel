from types import SimpleNamespace

import artin_sentinel.live as live


def test_rtsp_timeout_prefers_rtsp_specific_timeout(monkeypatch):
    live.ffmpeg_rtsp_timeout_args.cache_clear()
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        live.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout="  -rtsp_transport flags\n  -timeout <int64> set timeout in microseconds\n",
            stderr="",
        ),
    )
    assert live.ffmpeg_rtsp_timeout_args() == ("-timeout", "5000000")
    live.ffmpeg_rtsp_timeout_args.cache_clear()


def test_live_command_never_uses_rw_timeout(monkeypatch):
    live.ffmpeg_rtsp_timeout_args.cache_clear()
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(live, "ffmpeg_rtsp_timeout_args", lambda: ("-timeout", "5000000"))
    session = live.LiveStreamSession("rtsp://192.0.2.10/test")
    command = session._command(session.url)
    assert "-rw_timeout" not in command
    assert "-timeout" in command
    assert command[command.index("-timeout") + 1] == "5000000"


def test_no_timeout_option_is_safer_than_unsupported_rw_timeout(monkeypatch):
    live.ffmpeg_rtsp_timeout_args.cache_clear()
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        live.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="RTSP demuxer options without socket timeout", stderr=""),
    )
    assert live.ffmpeg_rtsp_timeout_args() == ()
    live.ffmpeg_rtsp_timeout_args.cache_clear()

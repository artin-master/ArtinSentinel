from pathlib import Path
from types import SimpleNamespace

import artin_sentinel.live as live
import artin_sentinel.recorder as recorder
from artin_sentinel import __version__


def test_release_0224():
    assert __version__ == "0.2.90"


def test_audio_slider_has_real_gain_above_unity():
    assert live.audio_gain_for_slider(0) == 0.0
    assert live.audio_gain_for_slider(75) == 1.0
    assert live.audio_gain_for_slider(100) == 2.0
    assert 0.65 < live.audio_gain_for_slider(50) < 0.68


def test_audio_commands_use_dynamic_volume_safe_unity_filter_when_pactl_exists(monkeypatch):
    monkeypatch.setattr(live.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"ffplay", "ffmpeg", "pactl"} else None)
    monkeypatch.setattr(live, "ffmpeg_audio_output_devices", lambda: frozenset({"pulse"}))
    monkeypatch.setattr(live, "ffmpeg_rtsp_timeout_args", lambda: ())
    sess = live.LiveAudioSession("rtsp://camera/main", volume=100, audio_confirmed=True, audio_codec="pcm_alaw", audio_sample_rate=8000)
    commands = sess._commands("rtsp://camera/main")
    ffplay = next(cmd for name, cmd in commands if name == "ffplay/SDL")
    assert "-af" in ffplay and "volume=1.000" in ffplay
    assert ffplay[ffplay.index("-volume") + 1] == "100"
    assert "-analyzeduration" in ffplay and "-probesize" in ffplay


def test_mhdx_preflight_preserves_legacy_channels_before_ip_extra(monkeypatch):
    calls = []
    def fake_probe(url, *args, **kwargs):
        calls.append(url)
        ok = "channel=4" in url
        return recorder.RtspProbeReport(ok, 200 if ok else 404, "ok" if ok else "no")
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", fake_probe)
    ch, _sub, _detail, _url = recorder._select_stream_profile("192.0.2.10", "admin", "pw", None)
    assert ch == 4
    first_by_channel = []
    for url in calls:
        for channel in range(1, 6):
            if f"channel={channel}" in url and channel not in first_by_channel:
                first_by_channel.append(channel)
    assert first_by_channel[:4] == [1, 2, 3, 4]
    assert 5 not in first_by_channel[:4]


def test_mhdx_channel5_is_proxy_route_not_direct_camera_dependency(monkeypatch):
    inv = SimpleNamespace(
        authenticated=True, ok=True, detail="CGI ChannelTitle listou 5 canal(is)",
        channels=tuple(SimpleNamespace(channel_id=i, name=f"Canal {i:02d}") for i in range(1, 6)),
    )
    monkeypatch.setattr(recorder, "probe_intelbras_channel_titles", lambda *a, **k: inv)
    monkeypatch.setattr(recorder, "_select_stream_profile", lambda *a, **k: (1, 0, "RTSP confirmado", "rtsp://seed"))
    def probe(url, *a, **k):
        ok = "channel=5" in url
        return recorder.RtspProbeReport(ok, 200 if ok else 404, "ok" if ok else "no")
    monkeypatch.setattr(recorder, "probe_rtsp_url_detailed", probe)
    monkeypatch.setattr(recorder, "_audio_fields_for_urls", lambda *a, **k: {})
    rows = recorder.scan_intelbras_channels("192.0.2.10", "admin", "pw", max_channels=5)
    ch5 = next(row for row in rows if row.channel == 5)
    assert ch5.available
    assert ch5.channel_kind == "ip"
    assert "channel=5" in ch5.rtsp_url
    # There is deliberately no direct camera IP parameter in the scan API.
    assert "camera_ip" not in recorder.scan_intelbras_channels.__code__.co_varnames


def test_main_volume_slider_uses_dynamic_non_restart_semantics():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "self.audio_volume_slider.setTracking(True)" in source
    assert "session.set_volume(value)" in source
    assert "session.restart_with_volume(value)" not in source
    assert "75 = nível original" in source

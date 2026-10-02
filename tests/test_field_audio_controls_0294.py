from pathlib import Path

import pytest

import artin_sentinel.live as live
import artin_sentinel.talkback as talkback


def test_microphone_gain_100_percent_keeps_unmodified_capture_and_roundtrips(tmp_path):
    assert talkback.microphone_gain_db_for_percent(100) == pytest.approx(0.0)
    assert talkback.microphone_gain_filters(0.0) == []
    prefs = talkback.AudioInputPreferences(gain_db=talkback.microphone_gain_db_for_percent(100))
    talkback.save_audio_input_preferences(tmp_path, prefs)
    assert talkback.load_audio_input_preferences(tmp_path).gain_db == pytest.approx(0.0)


def test_microphone_gain_above_100_increases_level_and_limits_peaks():
    gain_db = talkback.microphone_gain_db_for_percent(150)
    assert gain_db > 0
    filters = talkback.microphone_gain_filters(gain_db)
    assert filters[0].startswith("volume=")
    assert filters[1] == "alimiter=limit=0.95:level=false"
    assert talkback.microphone_gain_percent_for_db(gain_db) == 150
    assert talkback.microphone_gain_db_for_percent(200) == pytest.approx(6.0206, abs=0.001)


def test_listening_curve_is_independent_monotonic_muted_and_keeps_ceiling():
    gains = [live.audio_gain_for_slider(value) for value in range(101)]
    assert gains[0] == 0.0
    assert all(left <= right for left, right in zip(gains, gains[1:]))
    assert 0 < gains[10] < gains[20]
    assert gains[20] < gains[30] < gains[50] < gains[80]
    assert gains[100] == 2.0
    assert live.audio_filter_for_slider(0) == "volume=0.000"
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "self.audio_volume_slider.valueChanged.connect(self.change_live_audio_volume)" in source
    assert "self.microphone_gain_slider.valueChanged.connect(self.change_microphone_gain)" in source
    assert "self.microphone_gain_slider.setRange(50, 200)" in source


@pytest.mark.parametrize("transport", ["dvrip", "http", "netsdk"])
def test_talkback_capture_preserves_each_transport_format_and_applies_only_mic_gain(monkeypatch, transport):
    monkeypatch.setattr(talkback.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(talkback, "ffmpeg_microphone_inputs", lambda: frozenset({"pulse"}))
    kwargs = dict(microphone_backend="pulse", microphone_source="default", gain_db=0)
    if transport == "dvrip":
        session = talkback.XmDvripTalkbackSession("192.0.2.10", "u", "p", **kwargs)
        command = session._capture_commands()[0][1]
        expected_codec = "pcm_alaw"
    elif transport == "http":
        session = talkback.IntelbrasHttpTalkbackSession("192.0.2.10", "u", "p", **kwargs)
        command = session._capture_commands()[0][1]
        expected_codec = "pcm_alaw"
    else:
        session = talkback.IntelbrasNetSDKTalkbackSession(
            "192.0.2.10", "u", "p", test_mode="live-pcm-literal", **kwargs
        )
        command = session._capture_commands("pcm")[0][1]
        expected_codec = "pcm_s16le"
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-ar") + 1] == "8000"
    assert command[command.index("-c:a") + 1] == expected_codec
    assert "-af" not in command  # 100% applies no signal change.


def test_mibo_default_netsdk_demo_and_live_mic_modes_remain_distinct():
    default_mode = talkback.IntelbrasNetSDKTalkbackSession("192.0.2.11", "u", "p")
    assert default_mode._mode_description()[1] == "reference"
    live_mode = talkback.IntelbrasNetSDKTalkbackSession(
        "192.0.2.11", "u", "p", test_mode="live-pcm-literal"
    )
    assert live_mode._mode_description()[1] == "pcm"

from pathlib import Path

import artin_sentinel.talkback as talkback
from artin_sentinel import __version__
from artin_sentinel.live import DvripLiveStreamSession, create_live_stream_session
from artin_sentinel.recorder import channels_for_live_view
from artin_sentinel.talkback import AudioInputPreferences, XmDvripTalkbackSession
from artin_akdb import CORE_REVISION, record_by_legacy_key


def test_release_0229_and_akdb_revision():
    assert __version__ == "0.2.93"
    assert CORE_REVISION >= 10
    row = record_by_legacy_key("it-blue-x3-we2q")
    assert row is not None
    assert "xm-dvrip-opmonitor-multilens-experimental" in row.protocols
    assert "xm-dvrip-fixed-lenses-not-homologated" in row.negative_knowledge
    assert "xm-dvrip-talkback-not-field-validated" in row.negative_knowledge


def test_microphone_preferences_roundtrip_and_gain_clamp(tmp_path):
    prefs = AudioInputPreferences(
        backend="pulse",
        source="alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.mono-fallback",
        gain_db=6,
    )
    talkback.save_audio_input_preferences(tmp_path, prefs)
    loaded = talkback.load_audio_input_preferences(tmp_path)
    assert loaded == prefs
    (tmp_path / "audio-input-settings.json").write_text(
        '{"backend":"pulse","source":"default","gain_db":99}', encoding="utf-8"
    )
    assert talkback.load_audio_input_preferences(tmp_path).gain_db == 9


def test_logitech_style_pulse_source_and_gain_build_g711a_command(monkeypatch):
    monkeypatch.setattr(talkback.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(talkback, "ffmpeg_microphone_inputs", lambda: frozenset({"pulse"}))
    source = "alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.mono-fallback"
    sess = XmDvripTalkbackSession(
        "192.0.2.47", "admin", "pw",
        microphone_backend="pulse", microphone_source=source,
        microphone_label="Webcam C270 Mono", gain_db=6,
    )
    label, cmd = sess._capture_commands()[0]
    assert label == "Webcam C270 Mono"
    assert cmd[cmd.index("-f") + 1] == "pulse"
    assert cmd[cmd.index("-i") + 1] == source
    assert cmd[cmd.index("-af") + 1] == "volume=6dB"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-ar") + 1] == "8000"
    assert cmd[cmd.index("-c:a") + 1] == "pcm_alaw"


def test_audio_stop_and_microphone_scan_are_not_blocking_gui_source():
    live = Path("artin_sentinel/live.py").read_text(encoding="utf-8")
    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    stop_start = live.index("    def stop(self) -> None:", live.index("class LiveAudioSession"))
    stop_end = live.index("    def set_volume", stop_start)
    stop_block = live[stop_start:stop_end]
    assert ".join(" not in stop_block
    assert 'threading.Thread(target=reap, name="sentinel-audio-reaper", daemon=True).start()' in stop_block
    assert stop_block.index("proc.wait(timeout=0.7)") < stop_block.index("threading.Thread(target=reap")
    refresh_start = app.index("    def refresh_selected_audio_controls")
    refresh_end = app.index("    def ", refresh_start + 8)
    refresh_block = app[refresh_start:refresh_end]
    assert "ffmpeg_microphone_inputs()" not in refresh_block
    assert "self.microphone_inputs" in refresh_block
    assert "refresh_microphone_inputs_async" in app


def test_intelbras_known_channels_are_not_hidden_from_trees_or_detached_open_all():
    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'list_recorder_channels(int(device_id))' in app
    detached_start = app.index("    def open_all(self,device_id):")
    detached_end = app.index("    def source_context_menu", detached_start)
    block = app[detached_start:detached_end]
    assert "available_only=True" not in block
    assert "all_channels" in block and "channels_for_live_view(all_channels, identity.kind)" in block
    pending = [{"available": 0, "id": 1}]
    assert channels_for_live_view(pending, "dvr") == pending
    assert channels_for_live_view(pending, "nvr") == []
    assert "self.device_live_btn.setEnabled(bool(self.db.list_recorder_channels(device_id)))" in app


def test_native_dvrip_live_factory():
    session = create_live_stream_session(
        "dvrip://192.0.2.47:34567?channel=1&subtype=0", "admin", "pw"
    )
    assert isinstance(session, DvripLiveStreamSession)
    assert session._dvrip_target(session.url) == ("192.0.2.47", 34567, 1, 0)


def test_itblue_native_multilens_fallback_is_media_gated():
    src = Path("artin_sentinel/ip_camera.py").read_text(encoding="utf-8")
    assert "probe_dvrip_media(" in src
    assert 'f"dvrip://{ip}:34567?channel={native_channel}&subtype=0"' in src
    assert "if not main_probe.ok and not (sub_probe and sub_probe.ok):" in src
    assert "Vídeo nativo DVRIP" in src


def test_recorder_proxy_audio_can_be_rechecked_despite_stale_availability():
    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'recheckable_proxy = route_kind == "via_recorder" and channel_kind == "ip"' in app
    assert "or recheckable_proxy" in app

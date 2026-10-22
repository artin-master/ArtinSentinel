import json
from pathlib import Path
from types import SimpleNamespace

from artin_sentinel.akdb import audio_capability
from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.recorder import RecorderChannel
import artin_sentinel.live as live


def test_akdb_tracks_field_audio_capabilities():
    aitek = audio_capability(profile_key="aitek-sigma-seg6050bp")
    mibo = audio_capability(profile_key="intelbras-mibo")
    itblue = audio_capability(provider="it-blue")
    assert aitek["mode"] == "listen"
    assert "pcm_mulaw" in aitek["codecs"]
    assert mibo["mode"] == "bidirectional"
    assert mibo["talkback_protocol"] == "unvalidated"
    assert itblue["mode"] == "bidirectional"


def test_channel_audio_metadata_is_migrated_and_persisted(tmp_path):
    db = Database(tmp_path / "sentinel.db")
    site_id = db.list_sites()[0]["id"]
    device_id = db.upsert_device(Device(site_id=site_id, name="Aitek", ip="192.168.1.20", kind=DeviceKind.CAMERA, provider="aitek"))
    db.replace_recorder_channels(device_id, [RecorderChannel(
        1, "Câmera 01", "rtsp://192.168.1.20/live/0/MAIN", True,
        main_rtsp_url="rtsp://192.168.1.20/live/0/MAIN",
        sub_rtsp_url="rtsp://192.168.1.20/live/0/SUB",
        route_kind="direct", channel_kind="ip",
        audio_mode="listen", audio_codec="pcm_mulaw", audio_sample_rate=8000,
        audio_channels=1, audio_detail="pcm_mulaw 8000 Hz",
    )])
    row = db.list_recorder_channels(device_id)[0]
    assert row["audio_mode"] == "listen"
    assert row["audio_codec"] == "pcm_mulaw"
    assert row["audio_sample_rate"] == 8000
    assert row["audio_channels"] == 1
    db.close()


def test_ffmpeg_decoder_inventory_recognizes_hevc(monkeypatch):
    live.ffmpeg_decoders.cache_clear()
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(live.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=" VFS..D hevc                 HEVC (High Efficiency Video Coding)\n V..... h264                 H.264\n A....D pcm_mulaw            PCM mu-law\n",
        stderr="", returncode=0,
    ))
    assert live.local_decoder_available("hevc") is True
    assert live.local_decoder_available("h265") is True
    assert live.local_decoder_available("g711u") is True
    live.ffmpeg_decoders.cache_clear()


def test_rtsp_media_probe_extracts_audio_track(monkeypatch):
    monkeypatch.setattr(live.shutil, "which", lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None)
    monkeypatch.setattr(live, "ffmpeg_rtsp_timeout_args", lambda: ())
    payload = {"streams": [
        {"codec_type": "video", "codec_name": "hevc", "width": 800, "height": 448},
        {"codec_type": "audio", "codec_name": "pcm_mulaw", "sample_rate": "8000", "channels": 1},
    ]}
    monkeypatch.setattr(live.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=json.dumps(payload), stderr="", returncode=0,
    ))
    result = live.probe_rtsp_media_capabilities("rtsp://camera/live/0/SUB", "admin", "secret")
    assert result.ok is True
    assert result.video_codec == "hevc"
    assert result.audio_codec == "pcm_mulaw"
    assert result.audio_sample_rate == 8000
    assert result.has_audio is True


def test_live_ui_exposes_listen_and_safe_talkback_foundation():
    text = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "Ouvir janela selecionada" in text
    assert "Push-to-Talk" in text
    assert "self.audio_button" in text
    assert "self.talk_button" in text
    assert "LiveAudioSession" in text
    # 0.2.23 enables microphone transmission only for a model/profile whose
    # AKDB talkback transport is explicitly known; generic devices remain gated.
    assert '"xm-dvrip-g711a-experimental"' in text
    assert '"intelbras-http-postaudio-experimental"' in text
    assert "XmDvripTalkbackSession" in text

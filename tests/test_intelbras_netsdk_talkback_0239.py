from pathlib import Path
from artin_sentinel import __version__
from artin_sentinel.intelbras_netsdk import (
    IntelbrasNetSDK, TalkFormat, DH_TALK_PCM, DH_TALK_G711A,
    DH_TALK_ENCODE_TYPE, DH_TALK_SERVER_MODE, DH_TALK_SPEAK_PARAM,
    DH_TALK_TRANSFER_MODE, DH_TALK_TALK_CHANNEL,
)
from artin_sentinel.talkback import IntelbrasNetSDKTalkbackSession


def test_release_version_0239():
    assert __version__ == "0.2.94"


def test_vendor_demo_pcm_path_is_preferred():
    chosen = IntelbrasNetSDK.choose_talk_format([
        TalkFormat(DH_TALK_G711A, 8000, 8, 40),
        TalkFormat(DH_TALK_PCM, 8000, 16, 40),
    ])
    assert chosen.encode_type == DH_TALK_PCM
    assert chosen.sample_rate == 8000
    assert chosen.audio_bits == 16


def test_direct_talk_configuration_follows_vendor_server_mode_sequence():
    calls = []

    class FakeLib:
        def CLIENT_SetDeviceMode(self, handle, mode, value):
            calls.append((handle, mode, value))
            return 1

    sdk = object.__new__(IntelbrasNetSDK)
    sdk.lib = FakeLib()
    ok, detail = sdk.configure_direct_talk(99, TalkFormat(DH_TALK_PCM, 8000, 16, 40), 0)
    assert ok and detail.startswith("OK")
    assert [mode for _handle, mode, _value in calls[:5]] == [
        DH_TALK_ENCODE_TYPE,
        DH_TALK_SERVER_MODE,
        DH_TALK_SPEAK_PARAM,
        DH_TALK_TRANSFER_MODE,
        DH_TALK_TALK_CHANNEL,
    ]


def test_netsdk_pcm_packet_matches_official_linux_demo_shape():
    assert IntelbrasNetSDKTalkbackSession.PCM_FRAME_PREFIX == bytes.fromhex("00 00 01 f0 0c 02 80 02")
    assert IntelbrasNetSDKTalkbackSession.PCM_PAYLOAD_BYTES == 640
    assert len(IntelbrasNetSDKTalkbackSession.PCM_FRAME_PREFIX) + IntelbrasNetSDKTalkbackSession.PCM_PAYLOAD_BYTES == 648


def test_live_view_routes_imx_to_netsdk_without_known_bad_http_fallback():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'netsdk_direct_candidate = bool(' in source
    assert 'if netsdk_direct_candidate:' in source
    assert 'talkback_protocol = "intelbras-netsdk-talk-experimental"' in source
    assert 'talkback_protocol != "intelbras-netsdk-talk-experimental" or netsdk_info.available' in source


def test_live_view_ui_makes_disabled_mic_and_ptz_controls_explicit():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "MIC INDISPONÍVEL NESTE CANAL" in source
    assert "MIC INDISP." in source
    assert 'setObjectName("PtzCapabilityBadge")' in source
    assert 'move_caption = QLabel("MOVIMENTO")' in source
    assert 'speed_caption = QLabel("VELOCIDADE")' in source

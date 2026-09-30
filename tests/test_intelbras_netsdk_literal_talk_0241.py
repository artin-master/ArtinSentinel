from __future__ import annotations

import ctypes
from pathlib import Path

from artin_sentinel import __version__
from artin_sentinel.intelbras_netsdk import (
    IntelbrasNetSDK, TalkFormat, DH_TALK_PCM,
    DH_TALK_ENCODE_TYPE, DH_TALK_SERVER_MODE, DH_TALK_SPEAK_PARAM,
    DH_TALK_TRANSFER_MODE, DH_TALK_TALK_CHANNEL,
    DHDEV_TALKDECODE_INFO, NET_SPEAK_PARAM, NET_TALK_TRANSFER_PARAM,
)
from artin_sentinel.talkback import IntelbrasNetSDKTalkbackSession


def test_release_version_0241():
    assert __version__ == "0.2.89"


def _configured_variant(*, wait=False, speaker=0):
    calls = []
    captured = {}

    class FakeLib:
        def CLIENT_SetDeviceMode(self, handle, mode, value):
            calls.append(mode)
            if mode == DH_TALK_ENCODE_TYPE:
                obj = ctypes.cast(value, ctypes.POINTER(DHDEV_TALKDECODE_INFO)).contents
                captured['packet'] = obj.nPacketPeriod
                captured['rate'] = obj.dwSampleRate
                captured['bits'] = obj.nAudioBit
                captured['codec'] = obj.encodeType
            elif mode == DH_TALK_SPEAK_PARAM:
                obj = ctypes.cast(value, ctypes.POINTER(NET_SPEAK_PARAM)).contents
                captured['speaker'] = obj.nSpeakerChannel
                captured['wait'] = obj.bEnableWait
                captured['speak_mode'] = obj.nMode
            elif mode == DH_TALK_TRANSFER_MODE:
                obj = ctypes.cast(value, ctypes.POINTER(NET_TALK_TRANSFER_PARAM)).contents
                captured['transfer'] = obj.bTransfer
            elif mode == DH_TALK_TALK_CHANNEL:
                captured['channel'] = ctypes.cast(value, ctypes.POINTER(ctypes.c_int)).contents.value
            return 1

    sdk = object.__new__(IntelbrasNetSDK)
    sdk.lib = FakeLib()
    steps = []
    ok, detail = sdk.configure_direct_talk(
        99, TalkFormat(DH_TALK_PCM, 8000, 16, 0), 0,
        speaker_channel=speaker, enable_wait=wait, transfer=False,
        step_callback=steps.append,
    )
    return ok, detail, calls, captured, steps


def test_a1_matches_literal_linux_05_talk_setup():
    ok, detail, calls, captured, steps = _configured_variant()
    assert ok
    assert calls == [
        DH_TALK_ENCODE_TYPE, DH_TALK_SERVER_MODE, DH_TALK_SPEAK_PARAM,
        DH_TALK_TRANSFER_MODE, DH_TALK_TALK_CHANNEL,
    ]
    assert captured == {
        'packet': 0, 'rate': 8000, 'bits': 16, 'codec': DH_TALK_PCM,
        'speaker': 0, 'wait': 0, 'speak_mode': 0, 'transfer': 0, 'channel': 0,
    }
    assert any('ENCODE_TYPE • OK' in step and 'packetPeriod=0' in step for step in steps)
    assert any('SPEAK_PARAM • OK' in step and 'speaker=0' in step and 'wait=false' in step for step in steps)
    assert any('TALK_CHANNEL • OK' in step and 'channel=0' in step for step in steps)
    assert 'speaker=0' in detail and 'wait=false' in detail


def test_a2_changes_only_enable_wait():
    ok, _detail, _calls, captured, _steps = _configured_variant(wait=True)
    assert ok
    assert captured['packet'] == 0
    assert captured['speaker'] == 0
    assert captured['wait'] == 1
    assert captured['transfer'] == 0
    assert captured['channel'] == 0


def test_a3_changes_only_speaker_channel():
    ok, _detail, _calls, captured, _steps = _configured_variant(speaker=1)
    assert ok
    assert captured['packet'] == 0
    assert captured['speaker'] == 1
    assert captured['wait'] == 0
    assert captured['transfer'] == 0
    assert captured['channel'] == 0


def test_field_modes_map_to_literal_variants():
    base = dict(host='192.0.2.1', username='u', password='p')
    a1 = IntelbrasNetSDKTalkbackSession(**base, test_mode='literal-reference')._mode_description()
    a2 = IntelbrasNetSDKTalkbackSession(**base, test_mode='literal-reference-wait')._mode_description()
    a3 = IntelbrasNetSDKTalkbackSession(**base, test_mode='literal-reference-speaker1')._mode_description()
    assert a1[2].packet_period_ms == a2[2].packet_period_ms == a3[2].packet_period_ms == 0
    assert (a1[4], a1[5]) == (False, 0)
    assert (a2[4], a2[5]) == (True, 0)
    assert (a3[4], a3[5]) == (False, 1)


def test_ui_exposes_a1_a2_a3_and_no_longer_offers_mode3():
    source = Path('artin_sentinel/app.py').read_text(encoding='utf-8')
    assert 'A1 • Demo 05.Talk literal' in source
    assert 'A2 • Demo + aguardar dispositivo' in source
    assert 'A3 • Demo + speaker 1' in source
    assert 'D • V3/MODE3 + PCM' not in source

from __future__ import annotations

import io
from pathlib import Path
import tarfile
import zipfile

from artin_sentinel import __version__
from artin_sentinel import talkback
from artin_sentinel.intelbras_netsdk import (
    IntelbrasNetSDK,
    TalkFormat,
    DH_TALK_PCM,
    DH_TALK_G711A,
    DH_TALK_CLIENT_MODE,
    DH_TALK_ENCODE_TYPE,
    DH_TALK_MODE3,
    DH_TALK_TRANSFER_MODE,
    DH_TALK_TALK_CHANNEL,
    EM_DEV_PROTOCOL_V3,
    install_from_official_archive,
)
from artin_sentinel.talkback import IntelbrasNetSDKTalkbackSession, AudioInputPreferences


def test_release_version_0240():
    assert __version__ == "0.2.93"


def test_g711a_private_frame_header_matches_8khz_alaw_shape():
    payload = bytes(range(256)) + bytes(range(64))
    frame = IntelbrasNetSDKTalkbackSession._private_audio_frame(payload, "g711a")
    assert frame[:6] == bytes.fromhex("00 00 01 f0 0e 02")
    assert frame[6:8] == bytes((0x40, 0x01))  # 320 bytes, little endian
    assert frame[8:] == payload


def test_pcm_private_frame_matches_vendor_reference_prefix():
    payload = b"\0" * 640
    frame = IntelbrasNetSDKTalkbackSession._private_audio_frame(payload, "pcm")
    assert frame[:8] == bytes.fromhex("00 00 01 f0 0c 02 80 02")
    assert len(frame) == 648


def test_netsdk_test_mode_is_persisted(tmp_path):
    prefs = AudioInputPreferences(netsdk_talk_mode="live-g711a-server")
    talkback.save_audio_input_preferences(tmp_path, prefs)
    loaded = talkback.load_audio_input_preferences(tmp_path)
    assert loaded.netsdk_talk_mode == "live-g711a-server"


def test_v3_mode_uses_client_mode_and_mode3():
    calls = []

    class FakeLib:
        def CLIENT_SetDeviceMode(self, handle, mode, value):
            calls.append(mode)
            return 1

    sdk = object.__new__(IntelbrasNetSDK)
    sdk.lib = FakeLib()
    ok, detail = sdk.configure_direct_talk(
        99, TalkFormat(DH_TALK_PCM, 8000, 16, 40), 0,
        mode="v3", protocol_type=EM_DEV_PROTOCOL_V3, audio_port=60123,
    )
    assert ok
    assert calls[:4] == [DH_TALK_ENCODE_TYPE, DH_TALK_CLIENT_MODE, DH_TALK_MODE3, DH_TALK_TRANSFER_MODE]
    assert DH_TALK_TALK_CHANNEL in calls
    assert "V3" in detail


def _official_like_zip(path: Path):
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
        for name, payload in {
            "bin/libdhnetsdk.so": b"netsdk",
            "bin/libInfra.so": b"infra",
            "demo/05.Talk/localRecordAudio.dav": b"R" * 648,
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "NetSDK 3.050/Linux/General_NetSDK_Eng_Linux64_IS_V3.050.0000005.4.R.190306.tar.gz",
            tar_buf.getvalue(),
        )


def test_official_sdk_import_persists_runtime_and_reference_audio(tmp_path):
    archive = tmp_path / "General_NetSDK_3.050_PlaySDK_3.042.zip"
    target = tmp_path / "vendor"
    _official_like_zip(archive)
    imported = install_from_official_archive(archive, target)
    assert (target / "libdhnetsdk.so").read_bytes() == b"netsdk"
    assert (target / "libInfra.so").read_bytes() == b"infra"
    assert (target / "localRecordAudio.dav").read_bytes() == b"R" * 648
    assert "localRecordAudio.dav" in imported


def test_ui_exposes_provisioning_and_four_field_test_modes():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "Instalar / importar NetSDK Intelbras…" in source
    assert '"literal-reference"' in source
    assert '"literal-reference-wait"' in source
    assert '"literal-reference-speaker1"' in source
    assert '"live-pcm-literal"' in source
    assert '"live-g711a-server"' in source
    assert "Configuração → Atualizações" in source

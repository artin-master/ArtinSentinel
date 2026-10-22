import json
from pathlib import Path

import artin_sentinel.intelbras_http as ih
from artin_sentinel import __version__
from artin_sentinel.talkback import _format_postaudio_payload


def test_release_0238(release_version):
    assert __version__ == release_version


def test_post_audio_path_supports_vendor_framing_modes():
    single = ih.POST_AUDIO_PATH.format(httptype="singlepart", channel=1)
    multi = ih.POST_AUDIO_PATH.format(httptype="multipart", channel=1)
    assert "httptype=singlepart" in single
    assert "httptype=multipart" in multi
    assert single.endswith("channel=1")


def test_multipart_payload_matches_v381_shape_and_800_byte_audio_part():
    chunk = bytes([0xD5]) * 800
    payload = _format_postaudio_payload(chunk, "multipart", "BOUNDARY")
    assert payload.startswith(
        b"--BOUNDARY\r\nContent-Type: Audio/G.711A\r\nContent-Length: 800\r\n\r\n"
    )
    assert payload.endswith(chunk + b"\r\n")
    assert _format_postaudio_payload(chunk, "singlepart", "BOUNDARY") == chunk


class _FakeResponse:
    status = 200
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self, _limit=-1):
        return self._raw


class _FakeOpener:
    def __init__(self, payload: dict):
        self.payload = payload
        self.last_request = None
    def open(self, request, timeout=0):
        self.last_request = request
        return _FakeResponse(self.payload)


def test_v381_talkback_buffer_probe_uses_source_type_zero_and_zero_based_channel(monkeypatch):
    opener = _FakeOpener({"flag": False})
    monkeypatch.setattr(ih, "_build_digest_opener", lambda *_a, **_k: opener)
    flag, detail = ih.query_talkback_buffer_empty(
        "http://192.168.15.253", "admin", "secret", audio_channel=1,
    )
    assert flag is False
    assert "contém dados" in detail
    body = json.loads(opener.last_request.data.decode("utf-8"))
    assert body == {"channel": 0, "sourceType": 0}
    assert opener.last_request.full_url.endswith("/cgi-bin/api/devAudioDecode/empty")


def test_live_talkback_source_uses_truthful_confirmation_and_multipart_fallback():
    source = Path("artin_sentinel/talkback.py").read_text(encoding="utf-8")
    assert "Transmitindo • aguardando confirmação do equipamento" in source
    assert "Falando • buffer de talkback ativo" in source
    assert "singlepart encerrou cedo; tentando multipart V3.81" in source
    assert "HTTP 6/6" in source
    assert "proc.stdout.read(800)" in source
    assert "query_talkback_buffer_empty" in source

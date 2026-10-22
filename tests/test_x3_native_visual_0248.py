from types import SimpleNamespace

from artin_sentinel import xm_dvrip


def test_native_signature_decodes_video_and_not_just_media_header(monkeypatch):
    class Session:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def monitor_claim(self, channel, subtype):
            assert (channel, subtype) == (2, 0)

        def monitor_start(self, channel, subtype):
            assert (channel, subtype) == (2, 0)

        def read_media_packet(self):
            self.calls += 1
            if self.calls == 1:
                return 0xFC, bytes([0, 0, 1, 0xFC, 2, 0]) + bytes(10) + bytes(128 * 1024)
            raise AssertionError("Unexpected additional media read")

    captured = {}

    def decode(cmd, *, input, capture_output, timeout, check):
        captured["cmd"] = cmd
        captured["input"] = input
        return SimpleNamespace(returncode=0, stdout=bytes(range(144)))

    monkeypatch.setattr(xm_dvrip, "DvripSession", Session)
    monkeypatch.setattr(xm_dvrip.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(xm_dvrip.subprocess, "run", decode)
    sig = xm_dvrip.dvrip_frame_signature("192.0.2.47", "u", "p", channel=2)
    assert isinstance(sig, int)
    assert "h264" in captured["cmd"]
    assert len(captured["input"]) == 128 * 1024


def test_native_signature_requires_decoder(monkeypatch):
    monkeypatch.setattr(xm_dvrip.shutil, "which", lambda name: None)
    assert xm_dvrip.dvrip_frame_signature("192.0.2.47", "u", "p") is None

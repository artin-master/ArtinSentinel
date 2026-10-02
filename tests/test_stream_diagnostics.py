import json
from threading import Event
from types import SimpleNamespace

import pytest

import artin_sentinel.live as live
import artin_sentinel.stream_diagnostics as diagnostics


@pytest.fixture
def ffprobe(monkeypatch):
    monkeypatch.setattr(live.shutil, 'which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr(live, 'ffmpeg_rtsp_timeout_args', lambda: ())
    def respond(payload=None, error='', returncode=0):
        monkeypatch.setattr(live.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
            stdout=json.dumps(payload or {}), stderr=error, returncode=returncode))
    return respond


@pytest.mark.parametrize('error,code', [
    ('Server returned 401 Unauthorized', 'authentication'),
    ('Server returned 403 Forbidden', 'authentication'),
    ('404 Not Found', 'stream_not_found'),
    ('Connection timed out', 'timeout'),
    ('Connection refused', 'rtsp_unavailable'),
    ('503 Service Unavailable', 'rtsp_unavailable'),
    ('Decoder not found', 'codec_unsupported'),
    ('Invalid data found when processing input', 'invalid_response'),
    ('failure', 'other_error'),
])
def test_media_errors_are_classified_without_external_text(ffprobe, error, code):
    ffprobe(error=error + ' rtsp://admin:s3cret@camera/user=admin_password_s3cret', returncode=1)
    result = live.probe_rtsp_media_capabilities('rtsp://camera/main', 'admin', 's3cret')
    assert result.error_code == code
    assert not result.ok
    assert 's3cret' not in result.detail and 'rtsp://' not in result.detail


def test_timeout_is_distinct_from_missing_tool(ffprobe, monkeypatch):
    def timeout(*args, **kw):
        raise live.subprocess.TimeoutExpired(['ffprobe', 'secret'], 1)
    monkeypatch.setattr(live.subprocess, 'run', timeout)
    assert live.probe_rtsp_media_capabilities('rtsp://camera/main').error_code == 'timeout'
    monkeypatch.setattr(live.shutil, 'which', lambda _: None)
    assert live.probe_rtsp_media_capabilities('rtsp://camera/main').error_code == 'probe_unavailable'


@pytest.mark.parametrize('payload', [[], {'streams': 'bad'}, {'streams': ['bad']}, {'streams': []}])
def test_malformed_or_empty_media_is_not_success(ffprobe, payload):
    ffprobe(payload)
    result = live.probe_rtsp_media_capabilities('rtsp://camera/main')
    assert not result.ok
    assert result.error_code in {'invalid_response', 'stream_not_found'}


def test_video_and_audio_tracks_are_reported_independently(ffprobe):
    ffprobe({'streams': [
        {'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080},
        {'codec_type': 'audio', 'codec_name': 'pcm_alaw', 'sample_rate': '8000', 'channels': 1},
    ]})
    result = live.probe_rtsp_media_capabilities('rtsp://camera/main')
    assert result.video_codec == 'h264'
    assert result.audio_present and result.video_present
    assert result.audio_codec == 'pcm_alaw'
    assert result.audio_sample_rate == 8000 and result.audio_channels == 1


@pytest.mark.parametrize('decoder_known,video_decoder,audio_codec,expected', [
    (True, True, '', 'video_without_audio'),
    (True, False, 'aac', 'codec_unsupported'),
    (True, True, 'aac', 'ok'),
    (False, False, 'aac', 'ok'),  # Missing local inventory is not proof of incompatibility.
])
def test_saved_routes_main_sub_and_decoder_states(monkeypatch, decoder_known, video_decoder, audio_codec, expected):
    calls = []
    def probe(url, *args, **kw):
        calls.append(url)
        return live.MediaProbeResult(ok=True, video_codec='h264', audio_codec=audio_codec,
                                     video_present=True, audio_present=bool(audio_codec))
    monkeypatch.setattr(diagnostics, 'probe_rtsp_media_capabilities', probe)
    monkeypatch.setattr(diagnostics, 'ffmpeg_decoders', lambda: {'h264', 'aac'} if decoder_known else set())
    monkeypatch.setattr(diagnostics, 'local_decoder_available', lambda codec: video_decoder if codec == 'h264' else True)
    rows = [{'channel_no': 5, 'main_rtsp_url': 'rtsp://main', 'sub_rtsp_url': 'rtsp://sub'}]
    result = diagnostics.diagnose_saved_streams(rows, 'user', 'secret')
    assert calls == ['rtsp://main', 'rtsp://sub']
    assert [r.stream for r in result] == ['Main', 'Sub']
    assert all(r.state == expected for r in result)
    assert 'secret' not in repr(result)
    assert rows[0]['main_rtsp_url'] == 'rtsp://main'


def test_cancel_does_not_probe_or_modify_channels(monkeypatch):
    cancel = Event(); cancel.set()
    monkeypatch.setattr(diagnostics, 'ffmpeg_decoders', lambda: set())
    monkeypatch.setattr(diagnostics, 'probe_rtsp_media_capabilities', lambda *a, **kw: pytest.fail('unexpected probe'))
    assert diagnostics.diagnose_saved_streams([{'channel_no': 1}], cancel_event=cancel) == []


def test_missing_sub_is_reported_without_inventing_url(ffprobe, monkeypatch):
    ffprobe({'streams': [{'codec_type': 'video', 'codec_name': 'h264'}]})
    monkeypatch.setattr(diagnostics, 'ffmpeg_decoders', lambda: set())
    result = diagnostics.diagnose_saved_streams([{'channel_no': 1, 'rtsp_url': 'rtsp://camera/main'}])
    assert result[0].state == 'video_without_audio'
    assert result[1].state == 'stream_not_found'
    assert 'não verificado' in result[1].summary()

import artin_sentinel.recorder as recorder
from artin_sentinel.lan_discovery import _classify_signature


def test_digest_does_not_invent_algorithm_token_when_challenge_omits_it():
    header = recorder._digest_authorization(
        'Digest realm="Login to DVR", nonce="abc", qop="auth"',
        'admin', 'secret', 'DESCRIBE',
        'rtsp://192.0.2.10:554/cam/realmonitor?channel=1&subtype=0',
    )
    assert 'algorithm=' not in header
    assert 'qop=auth' in header


def test_digest_uses_next_cseq_and_can_confirm_absolute_uri(monkeypatch):
    calls = []

    def fake_request(host, port, target, method='DESCRIBE', authorization='', timeout=1.25, cseq=1):
        calls.append((authorization, cseq))
        if not authorization:
            return 401, {'www-authenticate': 'Digest realm="Login", nonce="abc", qop="auth"'}, ''
        return 200, {}, 'v=0\r\na=rtpmap:96 H264/90000\r\n'

    monkeypatch.setattr(recorder, '_rtsp_request', fake_request)
    result = recorder.probe_rtsp_url_detailed(
        'rtsp://192.0.2.10:554/cam/realmonitor?channel=1&subtype=0',
        'admin', 'secret', use_ffprobe=False,
    )
    assert result.ok
    assert result.auth_scheme == 'Digest'
    assert result.authenticated_status == 200
    assert calls[0][1] == 1
    assert calls[1][1] == 2


def test_ffprobe_can_confirm_when_internal_digest_is_rejected(monkeypatch):
    def fake_request(host, port, target, method='DESCRIBE', authorization='', timeout=1.25, cseq=1):
        if not authorization:
            return 401, {'www-authenticate': 'Digest realm="Login", nonce="abc", qop="auth"'}, ''
        return 401, {'www-authenticate': 'Digest realm="Login", nonce="def", qop="auth"'}, ''

    monkeypatch.setattr(recorder, '_rtsp_request', fake_request)
    monkeypatch.setattr(recorder.shutil, 'which', lambda name: '/usr/bin/ffprobe')
    monkeypatch.setattr(recorder, '_ffprobe_probe', lambda *a, **k: (True, 'ffprobe confirmou h264 1920x1080'))
    result = recorder.probe_rtsp_url_detailed(
        'rtsp://192.0.2.10:554/cam/realmonitor?channel=1&subtype=0',
        'admin', 'secret', use_ffprobe=True,
    )
    assert result.ok
    assert result.strategy == 'ffprobe/libavformat'
    assert result.ffprobe_ok


def test_mhdx_model_can_be_extracted_from_embedded_page_text():
    maker, model, kind, evidence = _classify_signature(
        '<title>Intelbras</title><script>var model="MHDX 1004";</script>'
    )
    assert maker == 'intelbras'
    assert model == 'MHDX 1004'
    assert str(kind) in ('xvr', 'dvr')
    assert any('modelo encontrado' in item for item in evidence)

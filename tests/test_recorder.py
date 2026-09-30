from artin_sentinel.recorder import _parse_digest_header, intelbras_channel_url


def test_digest_header_parse():
    parsed = _parse_digest_header('Digest realm="Login to 123", nonce="abc", qop="auth"')
    assert parsed["realm"] == "Login to 123"
    assert parsed["nonce"] == "abc"
    assert parsed["qop"] == "auth"


def test_intelbras_channel_url():
    assert intelbras_channel_url("192.168.1.10", 3, 1) == "rtsp://192.168.1.10:554/cam/realmonitor?channel=3&subtype=1"

from artin_sentinel.remote_access import discovered_web_url


def test_discovered_web_opens_only_same_host_without_credentials():
    assert discovered_web_url("http://192.0.2.10/", "192.0.2.10") == "http://192.0.2.10/"
    assert discovered_web_url("https://192.0.2.10:8443/config", "192.0.2.10") == "https://192.0.2.10:8443/config"
    assert discovered_web_url("http://192.0.2.11/", "192.0.2.10") == ""
    assert discovered_web_url("http://admin:senha@192.0.2.10/", "192.0.2.10") == ""
    assert discovered_web_url("rtsp://192.0.2.10/stream", "192.0.2.10") == ""
    assert discovered_web_url("javascript:alert(1)", "192.0.2.10") == ""
    assert discovered_web_url("http://192.0.2.10:invalid/", "192.0.2.10") == ""
    assert discovered_web_url("", "192.0.2.10") == ""

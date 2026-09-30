from artin_sentinel.onvif import _first_text

def test_extract_xaddrs():
    xml = "<d:XAddrs>http://192.0.2.4/onvif/device_service</d:XAddrs>"
    assert _first_text(xml, "XAddrs").startswith("http://192.0.2.4")

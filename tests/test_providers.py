from artin_sentinel.domain import Device
from artin_sentinel.providers import pick_provider, classify_from_scopes

def test_intelbras_provider():
    device = Device(ip="192.0.2.2", manufacturer="Intelbras")
    assert pick_provider(device).provider == "intelbras"

def test_hikvision_provider():
    device = Device(ip="192.0.2.3", manufacturer="Hikvision")
    assert pick_provider(device).provider == "hikvision"

def test_scope_model():
    _, manufacturer, model = classify_from_scopes([
        "onvif://www.onvif.org/name/CAM",
        "onvif://www.onvif.org/manufacturer/Intelbras",
        "onvif://www.onvif.org/model/VIP%201230",
    ])
    assert manufacturer == "Intelbras"
    assert model == "VIP 1230"

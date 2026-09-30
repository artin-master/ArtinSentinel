from artin_sentinel.lan_discovery import _classify_signature


def test_intelbras_http_signature():
    maker, _model, _kind, evidence = _classify_signature('<title>Intelbras</title> intelbras')
    assert maker == "intelbras"
    assert evidence

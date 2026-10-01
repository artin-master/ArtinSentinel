from pathlib import Path

import artin_sentinel.intelbras_http as ih
from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind


def test_candidate_bases_prefers_saved_web_endpoint():
    bases = ih._candidate_bases(
        "192.168.15.254",
        web_url="https://192.168.15.254:8443/index.html",
        open_ports=[80, 443],
    )
    assert bases[0] == "https://192.168.15.254:8443"
    assert "http://192.168.15.254" in bases
    assert "https://192.168.15.254" in bases


def test_parse_official_key_value_responses():
    assert ih._kv_value("version=2.0.0\n", "version") == "2.0.0"
    assert ih._int_value("result=2\n") == 2
    assert ih._int_value("result=0\n") == 0
    assert ih._int_value("garbage") is None


def test_probe_marks_postaudio_only_after_audio_output(monkeypatch):
    monkeypatch.setattr(ih, "_build_digest_opener", lambda *a, **k: object())

    def fake_get(_opener, url, _timeout):
        if ih.API_VERSION_PATH in url:
            return 200, "version=2.0.0\n", ""
        if ih.AUDIO_INPUT_PATH in url:
            return 200, "result=1\n", ""
        if ih.AUDIO_OUTPUT_PATH in url:
            return 200, "result=2\n", ""
        raise AssertionError(url)

    monkeypatch.setattr(ih, "_get_text", fake_get)
    report = ih.probe_intelbras_http_api("192.168.15.254", "admin", "secret")
    assert report.supported is True
    assert report.authenticated is True
    assert report.api_version == "2.0.0"
    assert report.audio_inputs == 1
    assert report.audio_outputs == 2
    assert report.post_audio_candidate is True
    persisted = report.as_metadata()
    assert "secret" not in repr(persisted)
    assert "authorization" not in repr(persisted).casefold()


def test_probe_keeps_postaudio_disabled_without_output(monkeypatch):
    monkeypatch.setattr(ih, "_build_digest_opener", lambda *a, **k: object())

    def fake_get(_opener, url, _timeout):
        if ih.API_VERSION_PATH in url:
            return 200, "version=2.0.0\n", ""
        return 200, "result=0\n", ""

    monkeypatch.setattr(ih, "_get_text", fake_get)
    report = ih.probe_intelbras_http_api("192.168.15.253", "admin", "secret")
    assert report.supported is True
    assert report.audio_outputs == 0
    assert report.post_audio_candidate is False


def test_probe_reports_auth_failure_without_trying_to_infer_support(monkeypatch):
    monkeypatch.setattr(ih, "_build_digest_opener", lambda *a, **k: object())
    monkeypatch.setattr(ih, "_get_text", lambda *_a, **_k: (401, "", 'Digest realm="Device"'))
    report = ih.probe_intelbras_http_api("192.168.15.254", "admin", "bad")
    assert report.reachable is True
    assert report.authenticated is False
    assert report.supported is False
    assert report.auth_scheme == "Digest"


def test_db_can_persist_sanitized_provider_probe(tmp_path):
    db = Database(tmp_path / "sentinel.db")
    site_id = db.add_site("Teste", "")
    device_id = db.upsert_device(Device(site_id=site_id, name="MHDX", ip="192.168.15.254", kind=DeviceKind.XVR))
    merged = db.merge_device_metadata(device_id, {
        "intelbras_http_api": {
            "supported": True,
            "api_version": "2.0.0",
            "audio_inputs": 1,
            "audio_outputs": 1,
            "post_audio_candidate": True,
        }
    })
    assert merged["intelbras_http_api"]["post_audio_candidate"] is True
    row = db.get_device(device_id)
    assert "intelbras_http_api" in row["metadata_json"]
    db.close()


def test_devices_ui_exposes_read_only_intelbras_probe():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "Testar API Intelbras (somente leitura)" in source
    assert "probe_intelbras_http_api" in source
    assert "nenhum áudio foi enviado neste teste" in source

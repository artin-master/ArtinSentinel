import json
from pathlib import Path

from artin_sentinel.compat_capture import build_compatibility_report, sanitize_url, write_report


def test_sanitize_rtsp_removes_credentials_and_host():
    value = sanitize_url('rtsp://admin:secret@192.168.15.254:554/cam/realmonitor?channel=1&subtype=0')
    assert 'admin' not in value
    assert 'secret' not in value
    assert '192.168.15.254' not in value
    assert '<device>:554' in value
    assert 'channel=1' in value


def test_build_capture_is_credential_free(tmp_path: Path):
    device = {
        'name': 'DVR Casa', 'detected_name': 'Intelbras', 'manufacturer': 'Intelbras',
        'model': 'MHDX 1004', 'firmware': 'x', 'kind': 'xvr', 'provider': 'intelbras',
        'identity_confidence': 95, 'status': 'online', 'onvif_url': 'http://192.168.15.254/onvif',
        'web_url': 'http://192.168.15.254', 'rtsp_url': '',
        'metadata_json': json.dumps({'open_ports':[80,554,37777], 'evidence':['Intelbras HTTP'], 'akdb_profile':'intelbras-mhdx'})
    }
    channels = [{
        'channel_no':1, 'source_name':'Canal 01', 'available':1, 'preferred_stream':'auto',
        'main_rtsp_url':'rtsp://admin:secret@192.168.15.254:554/cam/realmonitor?channel=1&subtype=0',
        'sub_rtsp_url':'rtsp://admin:secret@192.168.15.254:554/cam/realmonitor?channel=1&subtype=1',
        'rtsp_url':'', 'detail':'H264'
    }]
    report = build_compatibility_report(device, channels, sentinel_version='0.2.4')
    raw = json.dumps(report)
    assert 'secret' not in raw
    assert '192.168.15.254' not in raw
    assert report['summary']['channels_available'] == 1
    out = write_report(tmp_path/'capture.json', report)
    assert out.exists()

import io
import sys
import subprocess
import threading
from types import SimpleNamespace as NS

import artin_sentinel.live as live
import artin_sentinel.native_protocols as native
import artin_sentinel.recorder as recorder


def test_configured_ip_inventory_uses_explicit_ids_and_names(monkeypatch):
    xml = b'<InputProxyChannelList><InputProxyChannel><id>17</id><name>VIPC Intelbras</name></InputProxyChannel><InputProxyChannel><id>18</id><name></name></InputProxyChannel></InputProxyChannelList>'
    monkeypatch.setattr(native, '_hikvision_isapi_get', lambda *a, **k: (200, xml, 'http://device', 'OK'))
    inventory = native.probe_hikvision_input_proxy_channels('192.0.2.1', 'u', 'p')
    assert [(r.channel_id, r.name) for r in inventory.channels] == [(17, 'VIPC Intelbras'), (18, '')]
    assert all(r.online is None for r in inventory.channels)


def test_ip_ids_above_manual_scan_limit_are_not_renumbered(monkeypatch):
    monkeypatch.setattr(recorder, 'probe_hikvision_isapi_device_info', lambda *a, **k: NS(authenticated=True, manufacturer='Topway', model='DEFENDER 16-720T3', detail='OK'))
    monkeypatch.setattr(recorder, 'probe_hikvision_isapi_streaming_channels', lambda *a, **k: NS(stream_ids=(), physical_channels=(), detail='empty'))
    monkeypatch.setattr(recorder, 'probe_hikvision_isapi_video_inputs', lambda *a, **k: NS(inputs=(), detail='empty'))
    monkeypatch.setattr(recorder, 'probe_hikvision_input_proxy_status', lambda *a, **k: NS(channels=(), detail='empty'))
    monkeypatch.setattr(native, '_hikvision_isapi_get', lambda *a, **k: (200, b'<InputProxyChannelList><InputProxyChannel><id>17</id><name>VIPC Intelbras</name></InputProxyChannel><InputProxyChannel><id>18</id></InputProxyChannel></InputProxyChannelList>', 'http://device', 'OK'))
    calls = []
    def probe(url, *args):
        calls.append(url)
        return recorder.RtspProbeReport(True, 200, 'media')
    monkeypatch.setattr(recorder, 'probe_rtsp_url_detailed', probe)
    monkeypatch.setattr(recorder, '_audio_fields_for_urls', lambda *a: {})
    rows = recorder.scan_hikvision_channels('192.0.2.1', 'u', 'p', max_channels=16)
    assert [r.channel for r in rows] == [17, 18]
    assert rows[0].name == 'VIPC Intelbras'
    assert all(r.available and r.channel_kind == 'ip' for r in rows)
    assert sorted(calls) == ['rtsp://192.0.2.1:554/Streaming/Channels/1701', 'rtsp://192.0.2.1:554/Streaming/Channels/1801']


def test_immediate_eof_is_not_a_fifteen_second_watchdog(monkeypatch):
    session = live.LiveStreamSession('rtsp://device/main')
    child = subprocess.Popen([sys.executable, '-c', 'pass'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    monkeypatch.setattr(live.subprocess, 'Popen', lambda *a, **k: child)
    monkeypatch.setattr(session, '_command', lambda *a: ['unused'])
    # EOF is observable before poll() updates the exit status.
    monkeypatch.setattr(session, '_read_exact', lambda *a, **k: b'')
    assert not session._attempt_profile(session.url, 'Main')
    assert not any('Watchdog' in line for line in session.drain_diagnostics())


def test_attempt_closes_stderr_only_after_its_reader_finishes(monkeypatch):
    session = live.LiveStreamSession('rtsp://device/main')
    entered, closed = threading.Event(), threading.Event()
    class Reader(io.BytesIO):
        def readline(self, *a):
            entered.set()
            closed.wait(1)
            return super().readline(*a)
        def close(self):
            closed.set()
            return super().close()
    class Child:
        stdin = None
        stdout = io.BytesIO()
        stderr = Reader()
        def poll(self): return 0
        def wait(self, **k):
            closed.set()
            return 0
    child = Child()
    monkeypatch.setattr(live.subprocess, 'Popen', lambda *a, **k: child)
    monkeypatch.setattr(session, '_command', lambda *a: ['unused'])
    assert not session._attempt_profile(session.url, 'Main')
    assert entered.is_set()
    assert not any('leitor de diagnóstico' in line for line in session.drain_diagnostics())
    assert child.stderr.closed


def test_exact_topway_model_routes_protocol_without_rebranding():
    from artin_sentinel.device_intelligence import recorder_provider_hint
    from artin_sentinel.hik_recording import uses_hikvision_recordings
    row = {'manufacturer': 'Topway', 'model': 'DEFENDER 16-720T3', 'kind': 'dvr'}
    assert recorder_provider_hint(row) == 'hikvision'
    assert uses_hikvision_recordings(row)
    assert row['manufacturer'] == 'Topway'
    assert recorder_provider_hint(dict(row, model='Another model')) == 'generic'
    assert recorder_provider_hint(dict(row, metadata_json='{"recorder_protocol":"intelbras"}')) == 'intelbras'


def test_stop_while_reading_real_child_reaps_without_closed_pipe_errors(monkeypatch):
    session = live.LiveStreamSession('rtsp://device/main')
    monkeypatch.setattr(session, '_command', lambda *a: [sys.executable, '-c',
        'import sys,time;sys.stdout.buffer.write(bytes(%d));sys.stdout.buffer.flush();time.sleep(20)' % live.FRAME_SIZE])
    session.start()
    import time
    deadline = time.monotonic() + 3
    while session.frame_count == 0 and time.monotonic() < deadline:
        time.sleep(.01)
    assert session.frame_count > 0
    child = session._process
    session.stop()
    assert session.wait_closed(2)
    assert child.poll() is not None
    assert child.stderr.closed and child.stdout.closed
    assert not any('leitor de diagnóstico' in line for line in session.drain_diagnostics())


def test_configured_inventory_rejects_unexpected_xml_and_unbounded_ids(monkeypatch):
    for xml in [b'<html><InputProxyChannel><id>17</id></InputProxyChannel></html>',
                b'<InputProxyChannelList><InputProxyChannel><id>999999</id></InputProxyChannel><InputProxyChannel><source><id>18</id></source></InputProxyChannel></InputProxyChannelList>']:
        monkeypatch.setattr(native, '_hikvision_isapi_get', lambda *a, **k: (200, xml, 'http://device', 'OK'))
        assert not native.probe_hikvision_input_proxy_channels('192.0.2.1', 'u', 'p').channels


def test_status_without_online_is_pending_not_offline(monkeypatch):
    xml = b'<InputProxyChannelStatusList><InputProxyChannelStatus><id>18</id></InputProxyChannelStatus></InputProxyChannelStatusList>'
    monkeypatch.setattr(native, '_hikvision_isapi_get', lambda *a, **k: (200, xml, 'http://device', 'OK'))
    assert native.probe_hikvision_input_proxy_status('192.0.2.1', 'u', 'p').channels[0].online is None


def test_open_all_skips_explicit_analog_no_video_but_keeps_legacy_pending():
    disabled = {'available': 0, 'channel_kind': 'analog', 'detail': 'entrada analógica • NO VIDEO • sem sinal'}
    pending = {'available': 0, 'channel_kind': 'unknown', 'detail': ''}
    assert recorder.channels_for_live_view([disabled], 'dvr') == []
    assert recorder.channels_for_live_view([disabled, pending], 'dvr') == [pending]


def test_real_inactivity_still_triggers_watchdog(monkeypatch):
    session = live.LiveStreamSession('rtsp://device/main')
    monkeypatch.setattr(live, 'FRAME_INACTIVITY_TIMEOUT', .05)
    monkeypatch.setattr(session, '_command', lambda *a: [sys.executable, '-c', 'import time;time.sleep(20)'])
    assert not session._attempt_profile(session.url, 'Main')
    assert session.last_error_class == 'frame_timeout'
    assert any('Watchdog' in line for line in session.drain_diagnostics())

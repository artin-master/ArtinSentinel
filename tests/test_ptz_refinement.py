from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QSlider

import artin_sentinel.ptz as ptz
import artin_sentinel.app as app


@pytest.fixture
def ptz_window(monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = app.MainWindow.__new__(app.MainWindow)
    QMainWindow.__init__(window)
    window.selected_video_tile = SimpleNamespace(index=0)
    window.ptz_status_label = QLabel()
    window.ptz_speed_slider = QSlider()
    window.ptz_speed_slider.setRange(10, 100)
    window.ptz_speed_slider.setValue(45)
    window.ptz_hold_timer = QTimer(window)
    window.ptz_results = Queue()
    tasks = []
    window.ptz_executor = SimpleNamespace(submit=tasks.append)
    device = dict(id=1, ip='192.0.2.1', onvif_url='', name='Camera 1')
    context = (device, {}, {'backend': 'onvif'}, True, False)
    monkeypatch.setattr(window, '_ptz_context_for_tile', lambda tile: context)
    monkeypatch.setattr(window, '_credentials_for_device', lambda did: ('admin', 'secret'))
    monkeypatch.setattr(window, 'append_live_diagnostic', Mock())
    yield window, tasks, context
    window.ptz_hold_timer.stop()
    window.hide()
    window.deleteLater()
    application.processEvents()


def test_stop_uses_original_target_after_selection_changes(ptz_window, monkeypatch):
    window, tasks, context = ptz_window
    starts, stops = [], []
    monkeypatch.setattr(app, 'start_move_provider', lambda **kw: starts.append(kw) or 'start')
    monkeypatch.setattr(app, 'stop_device_provider', lambda **kw: stops.append(kw) or 'stop')
    window.start_selected_ptz_hold('left')
    context[0]['ip'] = '192.0.2.2'
    window.ptz_speed_slider.setValue(90)
    window.selected_video_tile = SimpleNamespace(index=1)
    window.stop_selected_ptz_hold()
    for task in tasks:
        task()
    assert starts[0]['ip'] == stops[0]['ip'] == '192.0.2.1'
    assert stops[0]['direction'] == 'left'
    assert stops[0]['speed'] == 0.45
    assert not window.ptz_hold_timer.isActive()
    assert window._ptz_hold_target is None


def test_unconfirmed_or_zoom_unsupported_never_starts_hold(ptz_window, monkeypatch):
    window, tasks, context = ptz_window
    window.start_selected_ptz_hold('zoom-in')
    assert not tasks
    monkeypatch.setattr(window, '_ptz_context_for_tile', lambda tile: (*context[:3], False, False))
    window.start_selected_ptz_hold('left')
    assert not tasks
    assert not window.ptz_hold_timer.isActive()


def test_move_failure_stops_renewal_and_sanitizes_exception(ptz_window, monkeypatch):
    window, tasks, _ = ptz_window
    def fail(**kw):
        raise RuntimeError('http://admin:secret@camera/?password=secret')
    monkeypatch.setattr(app, 'start_move_provider', fail)
    window.start_selected_ptz_hold('left')
    tasks[0]()
    window.poll_ptz_results()
    assert not window.ptz_hold_timer.isActive()
    assert len(tasks) == 2  # Stop is still queued, even when start timed out.
    assert 'secret' not in window.ptz_status_label.text()


@pytest.mark.parametrize('method', [ptz.start_move_provider, ptz.stop_device_provider, ptz.pulse_move_provider])
def test_unknown_backend_never_falls_back_to_onvif(method, monkeypatch):
    probe = Mock()
    monkeypatch.setattr(ptz, 'discover_onvif_ptz_context', probe)
    args = ('192.0.2.1', 'admin', 'pw', '')
    if method != ptz.stop_device_provider:
        args += ('left',)
    with pytest.raises(ValueError, match='Backend'):
        method(*args, backend='unavailable')
    probe.assert_not_called()


def test_onvif_profile_without_ptz_is_rejected(monkeypatch):
    monkeypatch.setattr(ptz, '_device_service_candidates', lambda *args: ['http://cam/device'])
    monkeypatch.setattr(ptz, '_post', lambda url, body, *args, **kw:
                        '<Capabilities/>' if 'GetCapabilities' in str(body) else
                        '<GetProfilesResponse><Profiles token="fixed"/></GetProfilesResponse>')
    with pytest.raises(RuntimeError, match='ONVIF PTZ indisponível'):
        ptz.discover_onvif_ptz_context('192.0.2.1', 'admin', 'pw')


def test_pulse_attempts_stop_when_move_raises(monkeypatch):
    context = ptz.OnvifPtzContext('device', 'media', 'ptz', 'token')
    monkeypatch.setattr(ptz, 'discover_onvif_ptz_context', lambda *a: context)
    monkeypatch.setattr(ptz, 'continuous_move', Mock(side_effect=TimeoutError))
    stop = Mock()
    monkeypatch.setattr(ptz, 'stop', stop)
    with pytest.raises(TimeoutError):
        ptz.pulse_move('192.0.2.1', 'admin', 'pw', '', 'left')
    stop.assert_called_once_with(context, 'admin', 'pw')


@pytest.mark.parametrize('speed', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_speed_is_rejected(speed):
    with pytest.raises(ValueError, match='Velocidade'):
        ptz._velocity('left', speed)


def test_generic_speed_dome_name_does_not_choose_native_ptz(ptz_window, monkeypatch):
    window, _, _ = ptz_window
    monkeypatch.undo()
    device = dict(id=1, manufacturer='Generic', model='', detected_model='', name='Speed Dome Ball', provider='generic')
    channel = dict(source_name='CAM 1', detail='', channel_no=1, route_kind='direct')
    window.selected_video_tile.source = dict(type='channel', device_id=1, channel_id=1)
    window.db = SimpleNamespace(get_device=lambda did: device, get_recorder_channel=lambda cid: channel)
    monkeypatch.setattr(window, '_selected_device_profile_key', lambda device: '')
    assert window._ptz_context_for_tile(window.selected_video_tile)[3] is False

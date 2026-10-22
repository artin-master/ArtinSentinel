from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
from artin_sentinel.app import MainWindow, VideoTile
from artin_sentinel.camera_events import CameraEvent


@pytest.fixture
def window(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    application = QApplication.instance() or QApplication([])
    w = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(w)
    w.db = Mock()
    w.db.get_device.return_value = {'site_id':1,'ip':'192.0.2.1','provider':'it-blue','model':'IT-Blue','firmware':'V5','metadata_json':'{"dvrip_event_channel_correlation":{"source":"physical_test","endpoint":"192.0.2.1","firmware":"V5","channels":[{"native_channel":0,"channel_id":10}]}}'}
    w.db.list_recorder_channels.return_value = [{'id':10,'rtsp_url':'dvrip://192.0.2.1?channel=0'}]
    w._credentials_for_device = Mock(return_value=('admin','secret'))
    w.current_site_id = 1
    w.video_tiles = [VideoTile(0),VideoTile(1)]
    for i,tile in enumerate(w.video_tiles):
        tile.set_source('Camera','','stream active',{'device_id':1,'channel_id':10+i})
    w.live_sessions = {0: Mock(), 1:Mock()}
    w.selected_video_tile = w.video_tiles[0]
    w.camera_event_status = QLabel()
    w._ensure_camera_events()
    worker = SimpleNamespace(events=Queue(),stop=Mock(),wait=Mock(return_value=True),snapshot=lambda:__import__('artin_sentinel.dvrip_events',fromlist=['EventDiagnostics']).EventDiagnostics(support='yes',active=True,state='active'))
    w._camera_event_workers[1] = worker
    w._camera_event_bindings[1] = (1,'192.0.2.1',{0:10})
    yield w,worker
    w.deleteLater()
    for tile in w.video_tiles: tile.deleteLater()
    application.processEvents()


def test_badge_start_stop_keeps_streams_and_never_opens_modal(window,monkeypatch):
    from artin_sentinel.app import QMessageBox
    monkeypatch.setattr(QMessageBox,'information',lambda *a:pytest.fail('no modal'))
    w,worker = window
    worker.events.put(CameraEvent('motion_start',0))
    w.poll_camera_events()
    assert w.video_tiles[0].camera_event_badge.text() == 'Movimento'
    assert w.video_tiles[1].camera_event_badge.text() == ''
    assert w.video_tiles[0].footer.text() == 'stream active'
    for session in w.live_sessions.values(): session.stop.assert_not_called()
    worker.events.put(CameraEvent('motion_stop',0))
    w.poll_camera_events()
    assert w.video_tiles[0].camera_event_badge.text() == ''


def test_unknown_channel_equipment_and_expiry(window):
    w,worker = window
    clock = [0]
    w._camera_event_state.clock = lambda:clock[0]
    worker.events.put(CameraEvent('human_start',99))
    w.poll_camera_events()
    assert all(tile.camera_event_badge.text() == '' for tile in w.video_tiles)
    assert 'Equipamento: Pessoa' in w.camera_event_status.text()
    clock[0] = 31
    w.poll_camera_events()
    assert 'Pessoa' not in w.camera_event_status.text()


def test_site_change_discards_queued_results_and_close_clears_badge(window):
    w,worker = window
    worker.events.put(CameraEvent('motion_start',0))
    w.current_site_id = 2
    w.poll_camera_events()
    w.db.add_camera_event.assert_not_called()
    worker.stop.assert_called_once()
    assert not w._camera_event_workers
    tile = w.video_tiles[0]
    tile.set_camera_event_badge('Movimento')
    tile.clear_source()
    assert tile.camera_event_badge.text() == ''


def test_selection_change_does_not_retarget_event(window):
    w,worker = window
    w.selected_video_tile = w.video_tiles[1]
    worker.events.put(CameraEvent('human_start',0))
    w.poll_camera_events()
    assert w.video_tiles[0].camera_event_badge.text() == 'Pessoa'
    assert w.video_tiles[1].camera_event_badge.text() == ''


def test_diagnostic_is_sanitized_and_channel_scoped(window):
    w,worker = window
    w.db.get_device.return_value['model'] = 'model secret password=hidden'
    worker.events.put(CameraEvent('motion_start',0))
    w.poll_camera_events()
    text = w.camera_event_diagnostic_text(1)
    assert 'secret' not in text and 'hidden' not in text
    assert 'motion_start' in text and 'Canal cadastrado: 10' in text
    assert 'assinatura aceita' in text
    assert 'estado físico' in text


def test_probe_start_stop_and_missing_credentials_no_modal(window,monkeypatch):
    w,old = window
    w._stop_camera_event_device(1)
    fake = Mock()
    fake.snapshot.return_value = __import__('artin_sentinel.dvrip_events',fromlist=['EventDiagnostics']).EventDiagnostics()
    monkeypatch.setattr('artin_sentinel.dvrip_events.EventWorker', lambda *a, **k: fake)
    w.toggle_camera_event_probe(True)
    fake.start.assert_called_once()
    assert w._camera_event_bindings[1][0:2] == (1,'192.0.2.1')
    w.toggle_camera_event_probe(False)
    fake.stop.assert_called_once()
    w._credentials_for_device.return_value = None
    w.toggle_camera_event_probe(True)
    assert 'credencial' in w.camera_event_status.text()
    assert not w._camera_event_workers


def test_shutdown_stops_owned_worker_and_repeated_stop_is_safe(window):
    w,worker = window
    worker.events.put(CameraEvent('motion_start',0))
    w.stop_camera_events()
    w.stop_camera_events()
    worker.stop.assert_called_once()
    assert not w._camera_event_workers
    w.db.add_camera_event.assert_not_called()


def test_local_evidence_never_promotes_homologation_and_no_profile_write(window):
    w,worker = window
    w.db.get_device.return_value['metadata_json'] = '{}'
    worker.events.put(CameraEvent('human_start',0))
    w.poll_camera_events()
    patches = [call.args[1] for call in w.db.merge_device_metadata.call_args_list]
    evidence = patches[-1]['dvrip_event_evidence']
    assert evidence['homologated'] is False
    assert evidence['physical_validation'] == 'pending'
    assert evidence['confidence'] == 'protocol_response_only'
    assert evidence['normalized_types_observed'] == ['human_start']
    assert 'secret' not in repr(patches)
    assert all(list(patch) == ['dvrip_event_evidence'] for patch in patches)


def test_visible_diagnostic_updates_without_discarding_stream_notes(window):
    from PySide6.QtWidgets import QPlainTextEdit
    w,worker = window
    w.live_diag_panel = QPlainTextEdit()
    w.live_diag_panel.show()
    w.append_camera_event_diagnostic(1)
    w.live_diag_panel.appendPlainText('Live View: stream intacto')
    worker.events.put(CameraEvent('motion_start',0))
    w.poll_camera_events()
    assert 'Último evento: motion_start' in w.live_diag_panel.toPlainText()
    assert 'Live View: stream intacto' in w.live_diag_panel.toPlainText()
    w.live_diag_panel.deleteLater()

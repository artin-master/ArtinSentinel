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
    w.db.get_device.return_value = {'site_id':1,'ip':'192.0.2.1'}
    w.db.list_recorder_channels.return_value = [{'id':10,'rtsp_url':'dvrip://192.0.2.1?channel=0'}]
    w.current_site_id = 1
    w.video_tiles = [VideoTile(0),VideoTile(1)]
    for i,tile in enumerate(w.video_tiles):
        tile.set_source('Camera','','stream active',{'device_id':1,'channel_id':10+i})
    w.live_sessions = {0: Mock(), 1:Mock()}
    w.selected_video_tile = w.video_tiles[0]
    w.camera_event_status = QLabel()
    w._ensure_camera_events()
    worker = SimpleNamespace(events=Queue(),stop=Mock(),wait=Mock(return_value=True),snapshot=lambda:SimpleNamespace(state='active'))
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

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QLabel

from artin_sentinel.app import MainWindow, VideoTile, DetachedMonitorWindow


@pytest.fixture
def window(monkeypatch):
    application = QApplication.instance() or QApplication([])
    w = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(w)
    host = QWidget(w)
    w.setCentralWidget(host)
    w.video_grid = QGridLayout(host)
    w.video_tiles = [VideoTile(i) for i in range(4)]
    for i, tile in enumerate(w.video_tiles):
        w.video_grid.addWidget(tile, i // 2, i % 2)
        tile.set_source(str(i), '', '', dict(type='channel', device_id=1, channel_id=i+1))
    w.selected_video_tile = w.video_tiles[0]
    w._focus_return_state = None
    w._primary_mosaic_fullscreen = False
    w.live_sessions = {}
    w.live_diag_lines = {}
    w.mic_traces = {}
    w.talkback_session = None
    w.talkback_tile_index = None
    w._talkback_resume_audio = False
    w.live_audio_session = None
    w.live_audio_tile_index = None
    w.live_activity = QLabel()
    w.live_diag_panel = QWidget()
    w.live_diag_panel.hide()
    for name in ('save_live_workspace', 'refresh_live_diagnostic_panel',
                 '_set_live_selection_summary', 'stop_live_audio',
                 'stop_selected_ptz_hold', 'refresh_stream_indicator_for_selected',
                 '_refresh_live_selection_from_tile', 'refresh_selected_audio_controls'):
        monkeypatch.setattr(w, name, Mock())
    monkeypatch.setattr(w, 'select_video_tile', lambda tile: setattr(w, 'selected_video_tile', tile))
    yield w
    w.hide()
    w.deleteLater()
    application.processEvents()


def test_remove_focused_tile_restores_every_slot_without_restarting_others(window):
    tile = window.video_tiles[0]
    other = Mock()
    closed = Mock()
    window.live_sessions = {0: closed, 1: other}
    window.focus_video_tile(tile)
    assert window.video_tiles[1].isHidden()
    window.remove_tile_source(tile)
    assert window._focus_return_state is None
    assert all(not t.isHidden() for t in window.video_tiles)
    assert window.video_grid.count() == 4
    assert tile.source is None or not tile.source
    closed.stop.assert_called_once()
    other.stop.assert_not_called()
    # Closing again cannot resurrect a session.
    window.close_tile_source(tile)
    assert 0 not in window.live_sessions
    closed.stop.assert_called_once()


@pytest.mark.parametrize('change', ['close', 'replace', 'rebuild', 'shutdown', 'audio', 'generation'])
def test_delayed_audio_resume_cannot_control_replaced_or_closed_source(window, change):
    tile = window.video_tiles[0]
    source = dict(tile.source)
    window.toggle_tile_audio = Mock()
    if change == 'close':
        tile.clear_source()
    elif change == 'replace':
        tile.source = dict(source, channel_id=90)
    elif change == 'rebuild':
        window.video_tiles = window.video_tiles[1:]
    elif change == 'shutdown':
        window._closing_app = True
    elif change == 'audio':
        window._audio_resume_generation = 1
    else:
        tile._stream_generation = 1
    window._resume_audio_after_talkback(tile, source, 0, 0)
    window.toggle_tile_audio.assert_not_called()


def test_audio_resume_accepts_unchanged_source_only_when_no_session_active(window):
    tile = window.video_tiles[0]
    window.toggle_tile_audio = Mock()
    window._resume_audio_after_talkback(tile, dict(tile.source), 0, 0)
    window.toggle_tile_audio.assert_called_once_with(tile)
    window.toggle_tile_audio.reset_mock()
    window.talkback_session = Mock()
    window._resume_audio_after_talkback(tile, dict(tile.source), 0, 0)
    window.toggle_tile_audio.assert_not_called()


def test_pause_reconnection_stops_all_channel_resources_without_removing_source(window):
    tile = window.video_tiles[0]
    video, talk = Mock(), Mock()
    window.live_sessions = {0: video}
    window.talkback_session, window.talkback_tile_index = talk, 0
    window._talkback_resume_audio = True
    window.live_audio_tile_index = 0
    window.pause_tile_reconnect(tile)
    assert tile.source['channel_id'] == 1
    assert 'pausada' in tile.footer.text()
    video.stop.assert_called_once()
    talk.stop.assert_called_once()
    window.stop_live_audio.assert_called_once()
    assert not window._talkback_resume_audio
    assert not window.live_sessions


def test_move_active_talkback_tracks_original_channel_and_stops_ptz(window, monkeypatch):
    a, b = window.video_tiles[:2]
    monkeypatch.setattr(b, 'mapFromGlobal', lambda point: QPoint(1, 1))
    window.talkback_session = Mock()
    window.talkback_tile_index = 0
    window._ptz_active_direction = "left"
    window.move_tile_source(a, QPoint())
    assert b.source['channel_id'] == 1
    assert window.talkback_tile_index == 1
    window.stop_selected_ptz_hold.assert_called_once()
    window.stop_tile_stream(b)
    window.talkback_session.stop.assert_called_once()


def test_closed_detached_window_cannot_resume_on_visibility_timer():
    stub = SimpleNamespace(_closed=True)
    DetachedMonitorWindow._sync_stream_visibility(stub)


def test_rebuild_while_focused_deletes_hidden_old_tiles_and_resets_focus(window, monkeypatch):
    old_tiles = list(window.video_tiles)
    deleted = []
    for tile in old_tiles:
        monkeypatch.setattr(tile, 'deleteLater', lambda t=tile: deleted.append(t))
    monkeypatch.setattr(window, 'apply_source_to_tile', Mock())
    window.bottom_notice = QLabel()
    window.focus_video_tile(old_tiles[0])
    window.rebuild_video_grid(4)
    assert deleted == old_tiles
    assert window._focus_return_state is None
    assert window.video_grid.count() == 4
    assert all(not t.isHidden() for t in window.video_tiles)


@pytest.mark.parametrize('mode', ['main', 'sub', 'auto'])
def test_stream_switch_preserves_existing_listening_preference_once(window, monkeypatch, mode):
    tile = window.video_tiles[0]
    window.db = Mock()
    window.live_audio_tile_index = 0
    window.live_audio_session = Mock()
    window.live_sessions = {0: Mock()}
    monkeypatch.setattr(window, 'apply_source_to_tile', Mock())
    monkeypatch.setattr(window, 'refresh_source_tree', Mock())
    monkeypatch.setattr(window, 'toggle_tile_audio', Mock())
    window.change_tile_stream(tile, mode)
    window.toggle_tile_audio.assert_called_once_with(tile)
    source = window.apply_source_to_tile.call_args.args[1]
    assert source.get('forced_stream') == (None if mode == 'auto' else mode)


def test_callbacks_and_open_requests_after_shutdown_do_nothing(window, monkeypatch):
    window._closing_app = True
    window.db = Mock()
    window._set_live_audio_bar = Mock()
    tile = window.video_tiles[0]
    window.poll_live_streams()
    window.apply_source_to_tile(tile, dict(tile.source))
    window.start_talkback_for_tile(tile)
    window._reset_audio_bar_if_idle(0)
    assert not window.db.mock_calls
    window._set_live_audio_bar.assert_not_called()


def test_stale_tile_cannot_open_video_or_talkback_in_new_grid(window):
    old = window.video_tiles.pop(0)
    window.db = Mock()
    window.apply_source_to_tile(old, dict(old.source))
    window.start_talkback_for_tile(old)
    assert not window.db.mock_calls


def test_shutdown_rejects_ptz_start_but_preserves_original_stop(window):
    window._closing_app = True
    window.ptz_executor = Mock()
    assert not window._submit_ptz('start', 'left')
    window.start_selected_ptz_hold('left')
    window.ptz_executor.submit.assert_not_called()
    target = dict(ip='192.0.2.1', username='admin', password='pw', onvif_url='',
                  speed=0.45, backend='dvrip', name='Camera', direction='left', source_key=(0, 1, 1))
    assert window._submit_ptz('stop', quiet=True, target=target)
    window.ptz_executor.submit.assert_called_once()


def test_detached_focus_rebuild_and_close_leave_no_hidden_tiles_or_visibility_retry():
    application = QApplication.instance() or QApplication([])
    database = Mock()
    database.list_sites.return_value = []
    database.list_devices.return_value = []
    controller = QMainWindow()
    controller.db, controller.current_site_id, controller.live_audio_volume = database, 1, 75
    w = DetachedMonitorWindow(controller, 'test')
    w.apply_source = Mock()
    first = w.video_tiles[0]
    first.set_source('Camera', '', '', dict(type='channel', device_id=1, channel_id=1))
    try:
        w.toggle_camera_fullscreen(first)
        assert w._individual_fullscreen_tile is first
        w.rebuild_grid(4)
        application.processEvents()
        assert w._individual_fullscreen_tile is None
        assert all(not t.isHidden() for t in w.video_tiles)
        w.close()
        w._streams_suspended = True
        w._sync_stream_visibility()
        w.poll_streams()
        assert not w.poll_timer.isActive() and not w.visibility_timer.isActive()
        assert not w.sessions and w.audio_session is None
    finally:
        w.close()
        w.deleteLater()
        controller.deleteLater()
        application.processEvents()


def test_turning_listening_off_then_on_keeps_previous_player_as_handoff_owner(window, monkeypatch):
    import artin_sentinel.app as app
    tile = window.video_tiles[0]
    old = Mock()
    window.live_audio_session, window.live_audio_tile_index = old, 0
    window.live_audio_volume = 75
    monkeypatch.setattr(window, 'stop_live_audio', MainWindow.stop_live_audio.__get__(window))
    monkeypatch.setattr(window, '_set_live_audio_bar', Mock())
    monkeypatch.setattr(window, 'append_live_diagnostic', Mock())
    window.stop_live_audio()
    old.stop.assert_called_once()
    assert window.live_audio_session is None
    monkeypatch.setattr(window, '_audio_context_for_tile', lambda tile: (
        dict(id=1), dict(audio_codec='aac', audio_sample_rate=8000),
        dict(can_listen=True), ['rtsp://camera/main']))
    monkeypatch.setattr(window, '_credentials_for_device', lambda did: ('admin', 'secret'))
    monkeypatch.setattr(window, '_audio_identity_text', lambda *a: 'Camera')
    constructor = Mock()
    monkeypatch.setattr(app, 'create_live_audio_session', constructor)
    window.toggle_tile_audio(tile)
    assert constructor.call_args.kwargs['previous_session'] is old
    constructor.return_value.start.assert_called_once()
    assert window._live_audio_previous_session is None

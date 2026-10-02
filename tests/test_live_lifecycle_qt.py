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
    window.move_tile_source(a, QPoint())
    assert b.source['channel_id'] == 1
    assert window.talkback_tile_index == 1
    window.stop_selected_ptz_hold.assert_called_once()
    window.stop_tile_stream(b)
    window.talkback_session.stop.assert_called_once()


def test_closed_detached_window_cannot_resume_on_visibility_timer():
    stub = SimpleNamespace(_closed=True)
    DetachedMonitorWindow._sync_stream_visibility(stub)

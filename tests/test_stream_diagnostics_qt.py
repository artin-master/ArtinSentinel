from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidget, QPushButton

from artin_sentinel.app import MainWindow
from artin_sentinel.live import MediaProbeResult
from artin_sentinel.stream_diagnostics import StreamDiagnostic


@pytest.fixture
def diagnostic_window(monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window._transient_dialogs = []
    workers = []
    monkeypatch.setattr(window, 'start_qt_worker', workers.append)
    monkeypatch.setattr(window, '_credentials_for_device', lambda did: ('admin', 'secret'))
    yield window, workers
    for dialog in list(window._transient_dialogs):
        dialog.hide()
    window.hide()
    window.deleteLater()
    application.processEvents()


def test_qt_results_stay_in_original_dialog_without_database_writes(diagnostic_window):
    window, workers = diagnostic_window
    device = {'id': 1, 'name': 'DVR'}
    row = {'device_id': 1, 'channel_no': 5, 'main_rtsp_url': 'rtsp://camera/main'}
    window.db = Mock()
    window.show_channel_stream_diagnostics(device, [row])
    row['main_rtsp_url'] = 'rtsp://different/selected'
    window.selected_video_tile = SimpleNamespace(source={'device_id': 2})
    worker = workers[0]
    assert worker.args[0][0]['main_rtsp_url'] == 'rtsp://camera/main'
    worker.signals.result.emit([StreamDiagnostic(5, 'Main', 'video_without_audio', MediaProbeResult(
        ok=True, video_codec='h264', video_present=True, audio_present=False))])
    table = window._transient_dialogs[0].findChild(QTableWidget, 'streamDiagnosticsTable')
    assert table.item(0, 0).text() == '5'
    assert table.item(0, 2).text() == 'Vídeo sem áudio'
    assert 'secret' not in table.item(0, 3).text()
    assert not window.db.mock_calls
    worker.signals.finished.emit()


def test_cancel_sets_event_without_writing_or_changing_saved_route(diagnostic_window):
    window, workers = diagnostic_window
    window.db = Mock()
    row = {'channel_no': 1, 'rtsp_url': 'rtsp://camera/main'}
    window.show_channel_stream_diagnostics({'id': 1, 'name': 'Camera'}, [row])
    dialog = window._transient_dialogs[0]
    cancel = next(button for button in dialog.findChildren(QPushButton) if button.text() == 'Cancelar teste')
    cancel.click()
    assert workers[0].kwargs['cancel_event'].is_set()
    assert row['rtsp_url'] == 'rtsp://camera/main'
    assert not window.db.mock_calls
    workers[0].signals.result.emit([])
    workers[0].signals.finished.emit()

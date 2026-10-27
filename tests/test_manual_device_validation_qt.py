"""Validate the current unified Equipment 2.0 add dialog under Qt offscreen."""
import json
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QMainWindow, QMessageBox,
)

from artin_sentinel.app import MainWindow
from artin_sentinel.db import Database
from artin_sentinel.remote_access import ACCESS_PRIVATE


@pytest.fixture
def manual_window(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.db = Database(tmp_path / "manual-equipment.db")
    window.current_site_id = window.db.list_sites()[0]["id"]
    window.session_credentials = {}
    window.credential_store = Mock()
    window.refresh_all = Mock()
    window.select_configuration_device = Mock()
    window._pause_monitor_for_recorder = Mock()
    window._resume_monitor_after_recorder = Mock()
    window._start_recorder_channel_scan = Mock()
    window._start_direct_camera_scan = Mock()
    monkeypatch.setattr(QMessageBox, "warning", Mock())
    try:
        yield window, application
    finally:
        window.db.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def run_manual_dialog(window, application, interaction):
    errors = []

    def interact():
        dialog = application.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog)
            interaction(dialog)
        except BaseException as exc:
            errors.append(exc)
        finally:
            if isinstance(dialog, QDialog) and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, interact)
    window.add_device_manual()
    if errors:
        raise errors[0]


@pytest.mark.parametrize("invalid_host", [
    "rtsp://host",
    "rtsp://dvr.loja.interno/live",
    "http://dvr.loja.interno/live",
])
def test_invalid_manual_address_preserves_dialog_then_saves_once(manual_window, invalid_host):
    window, application = manual_window

    def interaction(dialog):
        dialog.name.setText("DVR loja")
        dialog.host.setText(invalid_host)
        dialog.password.setText("fixture-only-password")
        dialog.manufacturer.setCurrentText("Hikvision")
        dialog.kind.setCurrentIndex(dialog.kind.findData("dvr"))
        dialog.connection.setCurrentIndex(dialog.connection.findData(ACCESS_PRIVATE))
        dialog.web_port.setValue(8080)
        dialog.rtsp_port.setValue(8554)

        buttons = dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(buttons.button(QDialogButtonBox.Save), Qt.LeftButton)
        assert dialog.isVisible()
        assert application.activeModalWidget() is dialog
        assert dialog.host.text() == invalid_host
        assert dialog.name.text() == "DVR loja"
        assert "IP" in dialog.access_state.text() or "endereço" in dialog.access_state.text().lower()
        assert dialog.focusWidget() is dialog.host
        assert dialog.host.selectedText() == invalid_host
        assert window.db.list_devices() == []
        window.refresh_all.assert_not_called()
        QMessageBox.warning.assert_not_called()

        dialog.host.setText("DVR.LOJA.INTERNO")
        QTest.mouseClick(buttons.button(QDialogButtonBox.Save), Qt.LeftButton)
        assert dialog.result() == QDialog.Accepted

    run_manual_dialog(window, application, interaction)

    rows = window.db.list_devices()
    assert len(rows) == 1
    saved = rows[0]
    assert saved["site_id"] == window.current_site_id
    assert saved["name"] == "DVR loja"
    assert saved["ip"] == "dvr.loja.interno"
    assert saved["kind"] == "dvr"
    assert saved["web_url"] == "http://dvr.loja.interno:8080"
    assert saved["rtsp_url"] == "rtsp://dvr.loja.interno:8554"
    meta = json.loads(saved["metadata_json"])
    assert meta["connection_mode"] == ACCESS_PRIVATE
    assert meta["recorder_protocol"] == "hikvision"
    window.refresh_all.assert_called_once_with()
    window._start_recorder_channel_scan.assert_called_once()


@pytest.mark.parametrize("invalid_first", [False, True])
def test_cancel_manual_dialog_never_writes(manual_window, invalid_first):
    window, application = manual_window

    def interaction(dialog):
        dialog.name.setText("DVR loja")
        dialog.host.setText("rtsp://host" if invalid_first else "192.0.2.10")
        dialog.password.setText("fixture-only-password")
        buttons = dialog.findChild(QDialogButtonBox)
        if invalid_first:
            QTest.mouseClick(buttons.button(QDialogButtonBox.Save), Qt.LeftButton)
            assert dialog.isVisible()
            assert window.db.list_devices() == []
        QTest.mouseClick(buttons.button(QDialogButtonBox.Cancel), Qt.LeftButton)
        assert dialog.result() == QDialog.Rejected

    run_manual_dialog(window, application, interaction)
    assert window.db.list_devices() == []
    window.refresh_all.assert_not_called()

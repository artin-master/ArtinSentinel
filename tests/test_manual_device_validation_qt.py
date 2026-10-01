from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QLineEdit,
    QMainWindow, QMessageBox,
)

from artin_sentinel.app import MainWindow
from artin_sentinel.domain import DeviceKind
from artin_sentinel.remote_access import ACCESS_PRIVATE


@pytest.fixture
def manual_window(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.current_site_id = 7
    window.db = Mock()
    window.db.upsert_device.return_value = 42
    window.db.get_device.return_value = {"archived": 0}
    window.refresh_all = Mock()
    monkeypatch.setattr(QMessageBox, "warning", Mock())
    try:
        yield window, application
    finally:
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


@pytest.mark.parametrize("invalid_index,invalid_value", [
    (1, "rtsp://host"),
    (2, "rtsp://dvr.loja.interno/live"),
    (3, "http://dvr.loja.interno/live"),
])
def test_invalid_manual_address_preserves_dialog_then_saves_once(
    manual_window, invalid_index, invalid_value,
):
    window, application = manual_window
    values = ["DVR loja", "DVR.LOJA.INTERNO", "https://dvr.loja.interno/config",
              "rtsp://dvr.loja.interno:554/live"]

    def interaction(dialog):
        fields = dialog.findChildren(QLineEdit)
        for field, value in zip(fields, values):
            field.setText(value)
        access, kind, protocol = dialog.findChildren(QComboBox)
        access.setCurrentIndex(1)
        kind.setCurrentIndex(2)
        protocol.setCurrentIndex(2)
        selections = [combo.currentIndex() for combo in (access, kind, protocol)]
        fields[invalid_index].setText(invalid_value)
        expected = list(values)
        expected[invalid_index] = invalid_value
        buttons = dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
        assert dialog.isVisible()
        assert application.activeModalWidget() is dialog
        assert [field.text() for field in fields] == expected
        assert [combo.currentIndex() for combo in (access, kind, protocol)] == selections
        assert dialog.focusWidget() is fields[invalid_index]
        assert fields[invalid_index].selectedText() == invalid_value
        assert not window.db.mock_calls
        window.refresh_all.assert_not_called()
        QMessageBox.warning.assert_called_once()
        fields[invalid_index].setText(values[invalid_index])
        QTest.mouseClick(buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
        assert dialog.result() == QDialog.Accepted

    run_manual_dialog(window, application, interaction)
    window.db.upsert_device.assert_called_once()
    device = window.db.upsert_device.call_args.args[0]
    assert device.site_id == 7
    assert device.name == values[0]
    assert device.ip == values[1].lower()
    assert device.web_url == values[2]
    assert device.rtsp_url == values[3]
    assert device.kind == DeviceKind.DVR
    assert device.metadata == {"connection_mode": ACCESS_PRIVATE, "recorder_protocol": "hikvision"}
    window.db.update_device_identity.assert_called_once()
    window.refresh_all.assert_called_once_with()


@pytest.mark.parametrize("invalid_first", [False, True])
def test_cancel_manual_dialog_never_writes(manual_window, invalid_first):
    window, application = manual_window

    def interaction(dialog):
        name, ip, web, rtsp = dialog.findChildren(QLineEdit)
        name.setText("DVR loja")
        ip.setText("rtsp://host" if invalid_first else "192.0.2.10")
        buttons = dialog.findChild(QDialogButtonBox)
        if invalid_first:
            QTest.mouseClick(buttons.button(QDialogButtonBox.Ok), Qt.LeftButton)
            assert dialog.isVisible()
        QTest.mouseClick(buttons.button(QDialogButtonBox.Cancel), Qt.LeftButton)
        assert dialog.result() == QDialog.Rejected

    run_manual_dialog(window, application, interaction)
    assert not window.db.mock_calls
    window.refresh_all.assert_not_called()

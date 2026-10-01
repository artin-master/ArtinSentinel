from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QLineEdit, QMainWindow,
    QTableWidgetItem, QTabWidget,
)

from artin_sentinel.app import MainWindow


@pytest.fixture
def equipment_window(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    # Build the actual Equipment tab without starting timers, network or storage.
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.config_tabs = QTabWidget(window)
    window.setCentralWidget(window.config_tabs)
    for name in (
        "build_sites_section", "build_equipment_log_panel",
        "_discovery_selection_changed", "_device_selection_changed",
        "add_found_from_devices", "edit_selected_device", "show_device_context_menu",
    ):
        monkeypatch.setattr(window, name, Mock())
    window.build_devices_tab()
    window.resize(1500, 1200)
    window.show()
    application.processEvents()
    try:
        yield window, application
    finally:
        # Bypass the production close flow, which requires app authentication.
        window.hide()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def populate_table(table):
    table.setRowCount(1)
    for column in range(table.columnCount()):
        table.setItem(0, column, QTableWidgetItem(f"value-{column}"))


@pytest.mark.parametrize("table_name", ["devices_found_table", "dev_table"])
def test_equipment_cells_cannot_be_edited_inline(equipment_window, table_name):
    window, application = equipment_window
    table = getattr(window, table_name)
    populate_table(table)
    table.setCurrentCell(0, 0)
    table.setFocus()
    assert table.editTriggers() == QAbstractItemView.NoEditTriggers

    QTest.keyClick(table, Qt.Key_F2)
    application.processEvents()
    assert table.state() != QAbstractItemView.EditingState
    assert not table.findChildren(QLineEdit)
    assert table.item(0, 0).text() == "value-0"


def test_equipment_selection_double_click_and_context_menu_are_preserved(equipment_window):
    window, application = equipment_window
    for table, selection_handler, double_click_handler in (
        (window.devices_found_table, window._discovery_selection_changed, window.add_found_from_devices),
        (window.dev_table, window._device_selection_changed, window.edit_selected_device),
    ):
        populate_table(table)
        assert table.selectionBehavior() == QAbstractItemView.SelectRows
        assert table.selectionMode() == QAbstractItemView.SingleSelection
        table.selectRow(0)
        application.processEvents()
        assert len(table.selectedItems()) == table.columnCount()
        selection_handler.assert_called()
        position = table.visualItemRect(table.item(0, 0)).center()
        QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=position)
        QTest.mouseDClick(table.viewport(), Qt.LeftButton, pos=position)
        application.processEvents()
        double_click_handler.assert_called_once_with()
        assert not table.findChildren(QLineEdit)

    assert window.dev_table.contextMenuPolicy() == Qt.CustomContextMenu
    position = QPoint(10, 10)
    window.dev_table.customContextMenuRequested.emit(position)
    window.show_device_context_menu.assert_called_once_with(position)

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


def populate_inventory(table, names):
    table.setRowCount(len(names))
    for row, name in enumerate(names):
        for column in range(table.columnCount()):
            value = name if column == 0 else f"field-{row}-{column}"
            table.setItem(row, column, QTableWidgetItem(value))


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


@pytest.mark.parametrize(
    "query,visible_count",
    [
        ("camera", 2),
        ("not-found", 0),
        ("  camera  ", 2),
        ("CAMERA", 2),
    ],
)
def test_inventory_filter_counter_shows_visible_and_total(equipment_window, query, visible_count):
    window, _application = equipment_window
    populate_inventory(window.dev_table, ["Camera Hall", "sensor 2", "CAMERA garage", "DVR Loja"])
    window._device_inventory_online_count = 3

    window.refresh_device_filter(query)

    assert sum(not window.dev_table.isRowHidden(row) for row in range(4)) == visible_count
    assert window.device_inventory_count.text() == f"{visible_count} de 4 exibidos • 3 online"


def test_clearing_inventory_filter_restores_site_counter(equipment_window):
    window, _application = equipment_window
    populate_inventory(window.dev_table, ["Camera Hall", "sensor 2", "CAMERA garage", "DVR Loja"])
    window._device_inventory_online_count = 3

    window.device_filter.setText("camera")
    assert window.device_inventory_count.text() == "2 de 4 exibidos • 3 online"

    window.device_filter.clear()
    assert window.device_inventory_count.text() == "4 cadastrado(s) • 3 online"
    assert all(not window.dev_table.isRowHidden(row) for row in range(4))


def test_inventory_counter_updates_when_rows_change_with_filter_active(equipment_window):
    window, _application = equipment_window
    populate_inventory(window.dev_table, ["Camera Hall", "DVR Loja"])
    window._device_inventory_online_count = 1

    window.device_filter.setText("camera")
    assert window.device_inventory_count.text() == "1 de 2 exibidos • 1 online"

    window.dev_table.item(1, 0).setText("Camera Garage")
    window.refresh_device_filter(window.device_filter.text())

    assert window.device_inventory_count.text() == "2 de 2 exibidos • 1 online"
    assert all(not window.dev_table.isRowHidden(row) for row in range(2))

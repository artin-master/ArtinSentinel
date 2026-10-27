import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtWidgets import QApplication
from artin_sentinel.equipment_editor import EquipmentEditorDialog
from artin_sentinel.ui_titanium import titanium_icon, titanium_mark


def _app():
    return QApplication.instance() or QApplication([])


def test_unified_editor_hikvision_enables_hcnet_and_blocks_cloud():
    _app()
    dialog=EquipmentEditorDialog(None,site_name="Mallet")
    dialog.manufacturer.setCurrentText("Hikvision")
    dialog.kind.setCurrentIndex(dialog.kind.findData("dvr"))
    dialog._sync_policy()
    assert dialog.sdk_port.isEnabled()
    assert dialog.sdk_port.value()==8000
    item=dialog.connection.model().item(dialog.cloud_option_index)
    assert item is not None and not item.isEnabled()
    dialog.close()


def test_unified_editor_intelbras_enables_netsdk_and_cloud():
    _app()
    dialog=EquipmentEditorDialog(None,site_name="Mallet")
    dialog.manufacturer.setCurrentText("Intelbras")
    dialog.kind.setCurrentIndex(dialog.kind.findData("xvr"))
    dialog._sync_policy()
    assert dialog.sdk_port.isEnabled()
    assert dialog.sdk_port.value()==37777
    item=dialog.connection.model().item(dialog.cloud_option_index)
    assert item is not None and item.isEnabled()
    dialog.close()


def test_titanium_vector_assets_render():
    _app()
    assert not titanium_icon("play",24).isNull()
    assert not titanium_icon("record",24).isNull()
    assert not titanium_mark(64).isNull()

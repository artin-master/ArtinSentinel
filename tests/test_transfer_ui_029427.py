from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import Qt
from test_selective_transfer_029427 import databases,add

def test_export_dialog_selection_and_optional_fields(databases):
    from artin_sentinel.config_transfer_ui import ExportDevicesDialog
    from artin_sentinel.config_portability import export_configuration
    app=QApplication.instance() or QApplication([])
    a,b=databases;sid=a.add_site('Casa');one=add(a,sid,'192.0.2.1','SERIAL-ONE');two=add(a,sid,'192.0.2.2','SERIAL-TWO')
    owner=QWidget();owner.db=a;dialog=ExportDevicesDialog(owner)
    for i in range(dialog.tree.topLevelItemCount()):
        site=dialog.tree.topLevelItem(i)
        for j in range(site.childCount()):
            item=site.child(j)
            if item.data(0,Qt.UserRole)==two:item.setCheckState(0,Qt.Unchecked)
    dialog.names.setChecked(False);dialog.streams.setChecked(False)
    data=export_configuration(a,**dialog.export_options())
    assert dialog.selected_ids()=={one}
    assert len(data['sites'][0]['devices'])==1
    assert data['sites'][0]['devices'][0]['name']=='192.0.2.1'
    dialog.reject();owner.close()

def test_preview_only_new_rows_are_selectable(databases):
    from artin_sentinel.config_transfer_ui import ImportPreviewDialog
    from artin_sentinel.config_portability import export_configuration
    app=QApplication.instance() or QApplication([])
    a,b=databases;s1=a.add_site('Casa');s2=b.add_site('Casa')
    add(a,s1,'192.0.2.1','OLD-SERIAL');add(a,s1,'192.0.2.2','NEW-SERIAL');add(b,s2,'192.0.2.1','OLD-SERIAL')
    before='\n'.join(b.conn.iterdump());owner=QWidget();owner.db=b
    dialog=ImportPreviewDialog(owner,export_configuration(a))
    assert len(dialog.selected_keys())==1
    for row in range(dialog.table.rowCount()):
        item=dialog.table.item(row,0)
        if item.checkState()!=Qt.Checked:assert not item.flags()&Qt.ItemIsUserCheckable
    assert '\n'.join(b.conn.iterdump())==before
    dialog.reject();owner.close()

def test_private_file_write_is_atomic_and_size_limit_preserves_previous_file(tmp_path,monkeypatch):
    from artin_sentinel import config_transfer_ui as transfer
    import json
    path=tmp_path/'inventory.json';transfer._write_private(path,{'sites':[]})
    original=path.read_bytes()
    assert json.loads(original)=={'sites':[]} and path.stat().st_mode&0o777==0o600
    monkeypatch.setattr(transfer,'MAX_FILE',1)
    import pytest
    with pytest.raises(ValueError):transfer._write_private(path,{'sites':[1]})
    assert path.read_bytes()==original
    assert sorted(p.name for p in tmp_path.iterdir())==['inventory.json']

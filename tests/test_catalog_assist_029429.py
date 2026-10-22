from datetime import datetime
from dataclasses import replace

def test_general_profile_validation_does_not_validate_hikvision_playback():
    from artin_sentinel.model_catalog import catalog_models
    row=next(r for r in catalog_models() if r['key']=='hikvision-ds-7216hghi-f1')
    assert row['model']=='DS-7216HGHI-F1'
    assert row['features']['playback']['status']=='pending'
    assert row['features']['export']['status']=='pending'
    assert row['features']['playback']['firmware']=='Não individualizado'

def test_assisted_registration_records_origin_and_never_invents_access():
    from artin_sentinel.domain import Device,DeviceKind
    from artin_sentinel.fingerprint import apply_device_fingerprint
    d=Device(name='192.0.2.1',ip='192.0.2.1',model='DS-7216HGHI-F1',manufacturer='Hikvision',metadata={'discovery_sources':['onvif-ws-discovery']})
    apply_device_fingerprint(d)
    assert d.kind==DeviceKind.DVR
    assert d.metadata['identity_evidence_v1']['observed']['model']=='DS-7216HGHI-F1'
    assert d.metadata['identity_evidence_v1']['akdb']['stable_id']
    assert not d.rtsp_url and not d.serial and not d.firmware
    assert d.metadata['registration_suggestions']['requires_verification']

def test_conflicting_commercial_brand_does_not_silently_reroute():
    from artin_sentinel.domain import Device,DeviceKind
    from artin_sentinel.fingerprint import apply_device_fingerprint
    d=Device(name='DVR antigo',model='DS-7216HGHI-F1',manufacturer='Outra Marca',provider='generic',kind=DeviceKind.UNKNOWN)
    apply_device_fingerprint(d)
    assert d.manufacturer=='Outra Marca' and d.provider=='generic'
    assert d.metadata['identity_conflicts']

def test_catalog_filter_and_real_manufacturer_dialog(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QWidget
    from artin_sentinel.knowledge_ui import ModelCatalogDialog,ManufacturersDialog
    from artin_akdb.brands import BrandRegistry
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.refresh_all=lambda:None
    catalog=ModelCatalogDialog(owner);catalog.search.setText('DS-7216HGHI-F1')
    leaf=catalog.tree.topLevelItem(0).child(0).child(0)
    catalog.tree.setCurrentItem(leaf)
    assert catalog.features.rowCount()==9
    assert 'DS-7216HGHI-F1' in catalog.heading.text()
    r=BrandRegistry(tmp_path/'akdb.db');dialog=ManufacturersDialog(owner,r)
    dialog.choose.setCurrentIndex(dialog.choose.findText('Intelbras'))
    dialog.color='#80DEEA';dialog.save()
    assert dialog.result()==1 and BrandRegistry(r.path).resolve('Intelbras').color=='#80DEEA'
    catalog.close();owner.close()

def test_reference_picker_fills_only_empty_fields_and_never_addresses():
    from PySide6.QtWidgets import QApplication,QWidget,QFormLayout,QLineEdit,QComboBox
    from artin_sentinel.registration_assist import add_reference_picker
    app=QApplication.instance() or QApplication([])
    host=QWidget();form=QFormLayout(host);manufacturer=QLineEdit();model=QLineEdit()
    kind=QComboBox();kind.addItem('Desconhecido','unknown');kind.addItem('DVR','dvr')
    protocol=QComboBox();protocol.addItem('Automático','');protocol.addItem('Hikvision','hikvision')
    picker=add_reference_picker(form,host,manufacturer,model,kind,protocol)
    index=next(i for i in range(picker.choice.count()) if 'DS-7216HGHI-F1' in picker.choice.itemText(i))
    picker.choice.setCurrentIndex(index);picker.apply()
    assert manufacturer.text()=='Hikvision' and model.text()=='DS-7216HGHI-F1'
    assert kind.currentData()=='dvr' and protocol.currentData()=='hikvision'
    manufacturer.setText('Marca corrigida');model.setText('Modelo corrigido');picker.apply()
    assert manufacturer.text()=='Marca corrigida' and model.text()=='Modelo corrigido'
    host.close()

def test_reference_does_not_mix_a_different_manual_brand_with_model_defaults():
    from PySide6.QtWidgets import QApplication,QWidget,QFormLayout,QLineEdit,QComboBox
    from artin_sentinel.registration_assist import add_reference_picker
    app=QApplication.instance() or QApplication([])
    host=QWidget();form=QFormLayout(host);manufacturer=QLineEdit('Outra marca');model=QLineEdit()
    kind=QComboBox();kind.addItem('Desconhecido','unknown');kind.addItem('DVR','dvr')
    protocol=QComboBox();protocol.addItem('Automático','');protocol.addItem('Hikvision','hikvision')
    picker=add_reference_picker(form,host,manufacturer,model,kind,protocol)
    picker.choice.setCurrentIndex(next(i for i in range(picker.choice.count()) if 'DS-7216HGHI-F1' in picker.choice.itemText(i)))
    picker.apply()
    assert not model.text() and not protocol.currentData() and kind.currentData()=='unknown'
    host.close()

def test_reused_ip_with_different_mac_is_a_registration_conflict():
    from artin_sentinel.registration_assist import registration_conflicts
    from artin_sentinel.domain import Device
    known={'mac':'02:11:22:33:44:55','serial':'DVR12345','uuid':''}
    device=Device(ip='192.0.2.1',mac='02:11:22:33:44:66',serial='DVR12345')
    assert any('MAC' in message for message in registration_conflicts(known,device))
    device.mac='02-11-22-33-44-55'
    assert not registration_conflicts(known,device)

def test_legacy_or_malformed_evidence_does_not_break_device_details():
    from artin_sentinel.registration_assist import evidence_summary
    for data in (None,[],{'identity_evidence_v1':{'observed':[],'sources':[None,1],'akdb':None},'registration_suggestions':[],'identity_conflicts':[1]}):
        assert isinstance(evidence_summary(data),str)

def test_actual_discovery_does_not_update_known_device_when_ip_has_new_mac(tmp_path):
    from types import SimpleNamespace as NS
    from PySide6.QtWidgets import QApplication,QTableWidget,QLabel,QPlainTextEdit
    from artin_sentinel.app import MainWindow
    from artin_sentinel.db import Database
    from artin_sentinel.domain import Device
    app=QApplication.instance() or QApplication([])
    db=Database(tmp_path/'sentinel.db');site=db.list_sites()[0]['id']
    did=db.upsert_device(Device(site_id=site,ip='192.0.2.1',name='DVR conhecido',mac='02:11:22:33:44:55',manufacturer='Hikvision'))
    before=dict(db.get_device(did))
    new=Device(site_id=site,ip='192.0.2.1',mac='02:11:22:33:44:66',manufacturer='Hikvision')
    host=NS(db=db,current_site_id=site,discovery_site_id=site,devices_found_status=QLabel(),devices_discovery_log=QPlainTextEdit(),
            devices_found_table=QTableWidget(0,6),_sync_selected_device_actions=lambda:None,_discovery_selection_changed=lambda:None)
    host.refresh_discovery_registration=lambda:MainWindow.refresh_discovery_registration(host)
    report=NS(site_id=site,interfaces=[],addresses_scanned=1,responsive_hosts=1,devices=[new],other_hosts=[],web_results={})
    MainWindow.discovery_done(host,report)
    assert dict(db.get_device(did))==before
    assert 'Conflito' in host.devices_found_table.item(0,4).text()
    assert len(db.list_devices(site))==1
    db.close()

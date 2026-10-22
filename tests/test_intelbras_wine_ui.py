import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import subprocess
import sys
import time
from PySide6.QtWidgets import QApplication,QMainWindow,QLineEdit,QDialogButtonBox,QLabel,QComboBox
from artin_sentinel.db import Database
from artin_sentinel.credential_store import CredentialStore
from test_intelbras_wine_manager import fake_process


def test_wine_onboarding_uses_managed_port_and_persists_route_not_password(tmp_path,monkeypatch,request):
    from artin_sentinel.intelbras_cloud_ui import open_bridge_dialog
    from artin_sentinel.intelbras_wine import WineTunnelManager
    from artin_sentinel import intelbras_wine
    app=QApplication.instance() or QApplication([])
    helper=fake_process(tmp_path)
    manager=WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',
        command_factory=lambda report,stop,port:[sys.executable,str(helper),str(report),str(stop),'ready','35551'])
    monkeypatch.setattr(intelbras_wine,'wine_manager',lambda:manager)
    request.addfinalizer(manager.shutdown)
    sdk=tmp_path/'sdk';sdk.mkdir()
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',
        str(Path(__file__).parent/'fixtures/cloud_sdk_fake.cpp'),'-o',str(sdk/'libdhnetsdk.so')],check=True)
    monkeypatch.setenv('FAKE_TRACE',str(tmp_path/'trace'))
    monkeypatch.setenv('FAKE_EXPECT_PORT','35551')
    host=QMainWindow();host.db=Database(tmp_path/'inventory.sqlite3')
    host.current_site_id=host.db.add_site('Wine')
    host.credential_store=CredentialStore();host.session_credentials={};host._transient_dialogs=[]
    host.bottom_notice=QLabel();host._credentials_for_device=lambda did:None;host.refresh_all=lambda:None
    host.recorder_executor=ThreadPoolExecutor(max_workers=1)
    host._release_transient_dialog=lambda d:host._transient_dialogs.remove(d)
    dialog=open_bridge_dialog(host,sdk_dir=sdk)
    assert dialog.findChild(QComboBox,'cloudMode').currentData()=='wine'
    for field,value in [('cloudSerial','TEST-SERIAL-PRIVATE'),('cloudUser','TEST-USER-PRIVATE'),('cloudPassword','TEST-PASSWORD-PRIVATE')]:
        dialog.findChild(QLineEdit,field).setText(value)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    deadline=time.monotonic()+5
    while dialog.isVisible() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    host.recorder_executor.shutdown(wait=True);app.processEvents()
    devices=host.db.list_devices();assert len(devices)==1, dialog.findChildren(QLabel)[-1].text()
    metadata=json.loads(devices[0]['metadata_json']);assert metadata['wine_managed'] is True
    channels=host.db.list_recorder_channels(devices[0]['id'])
    assert all(c['main_rtsp_url'].startswith('intelbras-wine://127.0.0.1:37777/') for c in channels)
    assert 'TEST-PASSWORD-PRIVATE' not in str(list(host.db.conn.iterdump()))
    assert len(manager.entries)==1
    assert all(entry.refs==0 and entry.alive() for entry in manager.entries.values())
    manager.shutdown();assert not manager.entries
    host.close()

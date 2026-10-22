"""Local policy and UI action guards; no network, OS users or DVRs."""
from pathlib import Path
import json
import pytest

def test_optional_policy_preserves_upgrade_and_enabled_starts_as_operator(tmp_path):
    from artin_sentinel.access_control import AccessControl,DEFAULT_PERMISSIONS
    control=AccessControl(tmp_path)
    assert not control.enabled and control.allows('device_edit')
    control.set_admin_password('admin-test-strong')
    assert control.unlock_admin('admin-test-strong')
    control.configure(True,DEFAULT_PERMISSIONS)
    fresh=AccessControl(tmp_path)
    assert fresh.enabled and not fresh.is_admin
    assert fresh.allows('playback') and not fresh.allows('device_edit')
    assert fresh.unlock_admin('admin-test-strong') and fresh.allows('device_edit')
    fresh.lock();assert not fresh.allows('device_edit')
    assert 'admin-test-strong' not in ''.join(p.read_text() for p in tmp_path.iterdir())
    assert all(p.stat().st_mode&0o777==0o600 for p in tmp_path.iterdir())

def test_operator_cannot_save_policy_and_corruption_denies(tmp_path):
    from artin_sentinel.access_control import AccessControl,DEFAULT_PERMISSIONS
    c=AccessControl(tmp_path);c.set_admin_password('admin-test-strong');c.unlock_admin('admin-test-strong');c.configure(True,DEFAULT_PERMISSIONS);c.lock()
    with pytest.raises(PermissionError):c.configure(False,DEFAULT_PERMISSIONS)
    c.path.write_text('{bad')
    c=AccessControl(tmp_path)
    assert c.enabled and not c.allows('playback') and not c.allows('unknown')

def test_admin_unlock_rate_limit_and_explicit_lock(tmp_path):
    from artin_sentinel.access_control import AccessControl,DEFAULT_PERMISSIONS
    now=[0.0];c=AccessControl(tmp_path,now=lambda:now[0]);c.set_admin_password('admin-test-strong');c.unlock_admin('admin-test-strong');c.configure(True,DEFAULT_PERMISSIONS);c.lock()
    for _ in range(5):assert not c.unlock_admin('wrong')
    assert not c.unlock_admin('admin-test-strong')
    now[0]=61;assert c.unlock_admin('admin-test-strong')
    c.lock();assert not c.is_admin

def test_guard_blocks_real_ui_entrypoints_before_any_side_effect(tmp_path,monkeypatch):
    from artin_sentinel.access_control import AccessControl,DEFAULT_PERMISSIONS
    from artin_sentinel.app import MainWindow
    from types import SimpleNamespace
    c=AccessControl(tmp_path);c.set_admin_password('admin-test-strong');c.unlock_admin('admin-test-strong')
    c.configure(True,{key:False for key in DEFAULT_PERMISSIONS});c.lock()
    messages=[];monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.information',lambda *args:messages.append(args))
    host=SimpleNamespace(access_control=c,manual_recording=None)
    for name in ('add_device_manual','edit_selected_device','play_selected_recording','export_selected_recording','save_live_photo','toggle_manual_recording','import_portable_configuration'):
        getattr(MainWindow,name)(host)
    assert len(messages)==7

def test_settings_dialog_sets_separate_password_and_returns_to_operator(tmp_path):
    from PySide6.QtWidgets import QApplication,QWidget,QLabel,QPushButton
    from artin_sentinel.access_control import AccessControl
    from artin_sentinel.access_control_ui import PermissionsDialog
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.access_control=AccessControl(tmp_path)
    owner.stop_playback_audio=lambda:None;owner.stop_playback_stream=lambda:None
    owner.access_role_label=QLabel();owner.access_role_button=QPushButton()
    dialog=PermissionsDialog(owner)
    dialog.enabled.setChecked(True);dialog.password.setText('admin-test-strong');dialog.confirm.setText('admin-test-strong')
    dialog.checks['export'].setChecked(True)
    dialog.save()
    assert dialog.result()==1
    assert owner.access_control.enabled and not owner.access_control.is_admin
    assert owner.access_control.allows('export') and not owner.access_control.allows('device_edit')
    assert owner.access_role_label.text()=='Operador'
    dialog.deleteLater();owner.deleteLater();app.processEvents()

def test_operator_export_cannot_include_audio_without_audio_export_permission(tmp_path,monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace as NS
    from artin_sentinel.access_control import AccessControl,DEFAULT_PERMISSIONS
    from artin_sentinel.app import MainWindow
    c=AccessControl(tmp_path);c.set_admin_password('admin-test-strong');c.unlock_admin('admin-test-strong')
    flags=dict(DEFAULT_PERMISSIONS,export=True);c.configure(True,flags);c.lock()
    host=NS(access_control=c,playback_device_combo=NS(currentData=lambda:1),db=NS(get_device=lambda _:{}),playback_export_worker=None,
        selected_playback_clip=lambda:('127.0.0.1',37777,1,datetime(2026,10,19,8),datetime(2026,10,19,9),('u','p')),
        playback_trim_start=None,playback_trim_end=None,selected_recording_row=lambda:None,recording_route=lambda *a,**k:'native',
        playback_export_quality=NS(currentData=lambda:'compact'),playback_export_silent=NS(isChecked=lambda:False))
    seen=[]
    monkeypatch.setattr('artin_sentinel.recording_export_profiles.export_note',lambda q,d,a:seen.append(a) or 'test')
    monkeypatch.setattr('PySide6.QtWidgets.QFileDialog.getSaveFileName',lambda *a:('',''))
    MainWindow.export_selected_recording(host)
    assert seen==[False]

def test_corrupt_admin_verifier_fails_closed_without_crashing(tmp_path):
    from artin_sentinel.access_control import AccessControl
    c=AccessControl(tmp_path)
    c.admin_auth.path.write_text('[]')
    assert not c.unlock_admin('any-password')
    assert not c.is_admin

def test_open_restore_dialog_rechecks_role_when_admin_returns_to_operator(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QMainWindow,QTableWidget,QPushButton
    from artin_sentinel.access_control import AccessControl,DEFAULT_PERMISSIONS
    from artin_sentinel.app import MainWindow
    from types import SimpleNamespace as NS
    app=QApplication.instance() or QApplication([]);calls=[]
    c=AccessControl(tmp_path);c.set_admin_password('admin-test-strong');c.unlock_admin('admin-test-strong');c.configure(True,DEFAULT_PERMISSIONS)
    host=QMainWindow();host.access_control=c
    host.db=NS(list_archived_sites=lambda:[{'id':1,'name':'Test','description':''}],archive_site=lambda *a:calls.append(a))
    host._transient_dialogs=[];host._release_transient_dialog=lambda d:None;host.refresh_all=lambda:None
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.information',lambda *a:None)
    MainWindow.show_archived_sites(host)
    table=host.findChild(QTableWidget);table.selectRow(0)
    c.lock()
    next(b for b in host.findChildren(QPushButton) if b.text()=='Restaurar').click()
    assert not calls
    for d in host._transient_dialogs:d.reject()
    host.close();host.deleteLater();app.processEvents()

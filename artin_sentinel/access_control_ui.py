"""Administrator elevation and optional common-operator permissions."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QCheckBox,QLineEdit,
    QDialogButtonBox,QInputDialog,QMessageBox)
from .access_control import PERMISSION_LABELS


def enter_admin(owner):
    control=owner.access_control
    if control.is_admin:return True
    password,ok=QInputDialog.getText(owner,'Acesso de administrador','Senha administrativa:',QLineEdit.Password)
    if not ok:return False
    accepted=control.unlock_admin(password);password=''
    if not accepted:
        QMessageBox.information(owner,'Acesso administrativo','Senha não aceita. Após cinco erros, aguarde um minuto antes de tentar novamente.')
        return False
    sync_ui(owner);return True


class PermissionsDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner;self.control=owner.access_control
        self.setWindowTitle('Acesso e permissões');self.setMinimumWidth(470)
        layout=QVBoxLayout(self)
        note=QLabel('Um perfil comum para operação e uma senha administrativa separada.\nA senha habitual continua sendo usada para entrar no Sentinel.')
        note.setWordWrap(True);layout.addWidget(note)
        self.enabled=QCheckBox('Ativar controle de administrador e operador')
        self.enabled.setChecked(self.control.enabled);layout.addWidget(self.enabled)
        layout.addWidget(QLabel('Permitir ao operador:'))
        self.checks={}
        for key,label in PERMISSION_LABELS.items():
            check=QCheckBox(label);check.setChecked(self.control.permissions[key]);layout.addWidget(check);self.checks[key]=check
        self.password_required=not self.control.admin_auth.configured
        layout.addWidget(QLabel('Defina a senha administrativa (mínimo 8 caracteres):' if self.password_required else 'Trocar senha administrativa (opcional; deixe vazio para manter):'))
        self.password=QLineEdit();self.confirm=QLineEdit()
        for edit,hint in ((self.password,'Nova senha administrativa'),(self.confirm,'Repita a senha administrativa')):
            edit.setEchoMode(QLineEdit.Password);edit.setPlaceholderText(hint);layout.addWidget(edit)
        self.error=QLabel('');self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Salvar permissões')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        layout.addWidget(QLabel('Configurações, atualizações e gestão de Sites exigem administrador.\nAo salvar, a sessão volta ao perfil de operador.'))

    def save(self):
        try:
            if self.password_required or self.password.text() or self.confirm.text():
                if self.password.text()!=self.confirm.text():raise ValueError('As senhas não coincidem.')
                password=self.password.text()
                self.control.set_admin_password(password)
                if not self.control.unlock_admin(password):raise ValueError('Não foi possível ativar o acesso administrativo.')
                password=''
            self.control.configure(self.enabled.isChecked(),{key:check.isChecked() for key,check in self.checks.items()})
        except (OSError,ValueError,PermissionError) as exc:
            self.error.setText(str(exc));return
        self.password.clear();self.confirm.clear()
        self.control.lock();sync_ui(self.owner);self.accept()


def open_settings(owner):
    control=owner.access_control
    if control.admin_auth.configured:
        if not enter_admin(owner):return
    else:
        # Confirm the existing application access before initial enrollment.
        from .app import password_dialog
        if owner.app_auth.configured and not password_dialog(owner.app_auth,'Configurar permissões','Digite a senha atual de acesso ao Sentinel:',parent=owner):return
    dialog=PermissionsDialog(owner)
    dialog.exec()


def toggle_role(owner):
    if owner.access_control.is_admin:
        owner.access_control.lock();sync_ui(owner)
    else:enter_admin(owner)


def sync_ui(owner):
    control=getattr(owner,'access_control',None)
    if control is None:return
    enabled=control.enabled
    label=getattr(owner,'access_role_label',None)
    if label is not None:label.setText('Administrador' if enabled and control.is_admin else 'Operador' if enabled else 'Controle de permissões desativado')
    button=getattr(owner,'access_role_button',None)
    if button is not None:
        button.setVisible(enabled);button.setText('Voltar ao operador' if control.is_admin else 'Entrar como administrador')
    nav=getattr(owner,'nav_group',None)
    if nav is not None and nav.button(owner.PAGE_PLAYBACK) is not None:nav.button(owner.PAGE_PLAYBACK).setEnabled(control.allows('playback'))
    if not control.allows('playback'):
        owner.stop_playback_stream()
        history=getattr(owner,'_recording_history_dialog',None)
        if history is not None:history.reject()
        timer=getattr(owner,'playback_day_search_timer',None)
        if timer is not None:timer.stop()
        if getattr(owner,'pages',None) is not None and owner.pages.currentIndex()==owner.PAGE_PLAYBACK:owner.show_page(owner.PAGE_LIVE)
    if not control.allows('recorded_audio'):
        owner.stop_playback_audio()
    for name,capability in [('playback_listen_check','recorded_audio'),('playback_export_btn','export'),('record_button','record')]:
        widget=getattr(owner,name,None)
        if widget is not None:widget.setEnabled(control.allows(capability))
    silent=getattr(owner,'playback_export_silent',None)
    if silent is not None:
        if not control.allows('export_audio'):silent.setChecked(True)
        silent.setEnabled(control.allows('export_audio'))
    if not control.allows('record'):
        recording=getattr(owner,'manual_recording',None)
        if recording is not None:recording.stop()
    if not control.allows('export'):
        cancel=getattr(owner,'playback_export_cancel',None)
        if cancel is not None:cancel.set()
    tabs=getattr(owner,'config_tabs',None)
    if tabs is not None:
        for index in range(tabs.count()):
            if tabs.tabText(index) in ('AKDB','Atualizações'):tabs.setTabEnabled(index,control.allows('admin'))
        if not control.allows('admin') and tabs.currentIndex()>=0 and not tabs.isTabEnabled(tabs.currentIndex()):tabs.setCurrentIndex(0)
    if not control.allows('device_edit'):
        cancel=getattr(owner,'channel_scan_cancel_event',None)
        if cancel is not None:cancel.set()
        for name in ('recorder_credentials_dialog','_camera_credentials_dialog','_cloud_bridge_dialog'):
            dialog=getattr(owner,name,None)
            if dialog is not None:dialog.reject()

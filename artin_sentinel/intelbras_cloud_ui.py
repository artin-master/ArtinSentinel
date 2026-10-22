"""Pilot onboarding for an operator-managed Intelbras Cloud bridge."""
from __future__ import annotations

import json
from threading import Event
from queue import Queue, Empty
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QSpinBox, QCheckBox, QDialogButtonBox,
    QComboBox, QPushButton, QFileDialog, QHBoxLayout, QWidget,
)
from .intelbras_cloud import normalize_serial, probe_bridge, register_bridge_inventory
from .live import sanitize_text


def _probe_wine(serial, remote, username, password, archive, *, sdk_dir, cancel, progress):
    from .intelbras_wine import wine_manager
    manager=wine_manager()
    if archive:manager.prepare(archive,cancel_event=cancel,progress=progress)
    with manager.acquire(serial,remote,cancel_event=cancel,progress=progress) as lease:
        return probe_bridge(lease.port,serial,username,password,sdk_dir=sdk_dir,cancel_event=cancel)


def open_bridge_dialog(window, device=None, *, sdk_dir=None, initial_mode=None):
    from .access_control import authorize
    if not authorize(window,'device_edit' if device is not None else 'device_add'):return
    existing = getattr(window, '_cloud_bridge_dialog', None)
    if existing is not None:
        existing.raise_()
        existing.activateWindow()
        return existing
    dialog = QDialog(window)
    dialog.setWindowTitle('Intelbras Cloud • conexão por serial')
    dialog.setModal(True)
    dialog.setMinimumWidth(450)
    form = QFormLayout(dialog)
    info = QLabel('Wine automático abre o túnel pelo serial neste Linux, sem VM ou SIM Next. '
                  'As credenciais abaixo são as do DVR. Ponte externa mantém o modo anterior.')
    info.setWordWrap(True)
    form.addRow(info)
    metadata = json.loads(device['metadata_json'] or '{}') if device is not None else {}
    mode=QComboBox()
    mode.setObjectName('cloudMode')
    mode.addItem('Wine automático • sem VM','wine')
    mode.addItem('Ponte externa • modo anterior','external')
    selected=initial_mode or ('wine' if device is None or metadata.get('wine_managed') else 'external')
    mode.setCurrentIndex(mode.findData(selected))
    form.addRow('Conexão',mode)
    archive=QLineEdit()
    archive.setObjectName('cloudWineZip')
    archive.setPlaceholderText('Opcional após preparar; selecione SIMNextWINInstall.zip se solicitado')
    choose=QPushButton('Selecionar ZIP…')
    choose.clicked.connect(lambda: archive.setText(QFileDialog.getOpenFileName(dialog,'Bibliotecas Intelbras',filter='ZIP (*.zip)')[0] or archive.text()))
    row=QWidget();line=QHBoxLayout(row);line.setContentsMargins(0,0,0,0)
    line.addWidget(archive);line.addWidget(choose)
    form.addRow('Bibliotecas Wine',row)
    name = QLineEdit(device['name'] if device is not None else 'DVR remoto')
    serial = QLineEdit(metadata.get('cloud_serial', ''))
    serial.setObjectName('cloudSerial')
    serial.setReadOnly(device is not None)
    port = QSpinBox()
    port.setRange(1, 65535)
    port.setValue(int(metadata.get('bridge_port') or (37777 if selected=='wine' else 55162)))
    port.setObjectName('cloudPort')
    user, password = QLineEdit('admin'), QLineEdit()
    user.setObjectName('cloudUser')
    password.setObjectName('cloudPassword')
    password.setEchoMode(QLineEdit.Password)
    saved = window._credentials_for_device(device['id']) if device is not None else None
    if saved:
        user.setText(saved[0])
        password.setText(saved[1])
    save = QCheckBox('Salvar credencial no cofre seguro')
    save.setChecked(bool(device is not None and device['credential_saved']))
    save.setEnabled(window.credential_store.available)
    for label, widget in [('Nome', name), ('Serial do DVR', serial), ('Porta local da ponte', port),
                          ('Usuário do DVR', user), ('Senha do DVR', password), ('', save)]:
        form.addRow(label, widget)
    port_label=form.labelForField(port)
    def mode_changed():
        managed=mode.currentData()=='wine'
        row.setVisible(managed)
        port_label.setText('Porta de serviço do DVR' if managed else 'Porta local da ponte')
        port.setValue(37777 if managed else 55162)
    mode.currentIndexChanged.connect(mode_changed)
    row.setVisible(selected=='wine')
    port_label.setText('Porta de serviço do DVR' if selected=='wine' else 'Porta local da ponte')
    status = QLabel('Uma tentativa de login; abra os canais depois para confirmar imagem.')
    status.setWordWrap(True)
    form.addRow(status)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText('Conectar')
    form.addRow(buttons)
    state = dict(busy=False, closed=False)
    cancel = Event()
    fields = (name, serial, port, user, password, mode, archive, choose)
    window._cloud_bridge_dialog = dialog
    window._transient_dialogs.append(dialog)

    def release():
        if getattr(window, '_cloud_bridge_dialog', None) is dialog:
            window._cloud_bridge_dialog = None
        window._release_transient_dialog(dialog)

    def finished(_result):
        state['closed'] = True
        cancel.set()
        if not state['busy']:
            release()

    def connect():
        if not authorize(window,'device_edit' if device is not None else 'device_add'):return
        try:
            identifier = normalize_serial(serial.text())
            if not user.text() or not password.text():
                raise ValueError('Informe o usuário e a senha do DVR.')
        except ValueError as exc:
            status.setText(str(exc))
            return
        selected_site = window.current_site_id
        if selected_site is None:
            status.setText('Selecione um Site antes de cadastrar o DVR.')
            return
        values = (name.text().strip(), identifier, port.value(), user.text(), password.text(), save.isChecked())
        managed=mode.currentData()=='wine'
        archive_path=archive.text().strip() if managed else ''
        messages=Queue()
        state['busy'] = True
        buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        for field in fields:
            field.setEnabled(False)
        save.setEnabled(False)
        status.setText('Preparando a ponte Wine…' if managed else 'Conectando à ponte e conferindo a identidade do DVR…')

        def result(report):
            if state['closed'] or cancel.is_set() or getattr(window, '_closing_app', False):
                return
            title, identifier, endpoint, username, secret, persist = values
            prior = window.db.find_device_by_site_ip(selected_site, identifier)
            if not authorize(window,'device_edit' if prior is not None else 'device_add',notify=False):return
            restart = False
            if prior is not None:
                previous = json.loads(prior['metadata_json'] or '{}')
                restart = (previous.get('bridge_port') != endpoint or bool(previous.get('wine_managed')) != managed
                           or window._credentials_for_device(prior['id']) != (username, secret))
            try:
                did = register_bridge_inventory(window.db, selected_site, title, identifier,
                                                endpoint, report['channels'], managed=managed)
            except (ValueError, RuntimeError) as exc:
                status.setText(sanitize_text(str(exc), username, secret))
                return
            window.session_credentials[did] = (username, secret)
            stored = False
            notice = 'Credencial disponível somente nesta sessão.'
            if persist:
                outcome = window.credential_store.set_password(did, secret)
                stored = outcome.ok
                notice = outcome.message
            elif prior is not None and prior['credential_saved']:
                window.credential_store.delete_password(did)
            window.db.update_device_credential_meta(did, username, stored)
            if restart:
                window._restart_changed_live_sources(
                    did, {ch['id'] for ch in window.db.list_recorder_channels(did)})
            window.refresh_all()
            window.bottom_notice.setText(
                f'{"Cloud via Wine" if managed else "Cloud via ponte"} • {report["channels"]} canais inventariados. Abra um canal no mosaico. {notice}')
            dialog.accept()

        def error(message):
            if not state['closed'] and not getattr(window, '_closing_app', False):
                status.setText(sanitize_text(message, values[3], values[4]))

        def completed():
            state['busy'] = False
            if state['closed']:
                release()
                return
            buttons.button(QDialogButtonBox.Ok).setEnabled(True)
            for field in fields:
                field.setEnabled(True)
            save.setEnabled(window.credential_store.available)

        if managed:
            future=window.recorder_executor.submit(_probe_wine,values[1],values[2],values[3],values[4],archive_path,
                sdk_dir=sdk_dir,cancel=cancel,progress=messages.put)
        else:
            future=window.recorder_executor.submit(probe_bridge,values[2],values[1],values[3],values[4],
                sdk_dir=sdk_dir,cancel_event=cancel)
        timer = QTimer(window)
        timer.setInterval(50)

        def poll():
            while not messages.empty():
                try:message=messages.get_nowait()
                except Empty:break
                if not state['closed']:status.setText(message)
            if not future.done():
                return
            timer.stop()
            try:
                result(future.result())
            except Exception as exc:
                error(str(exc))
            finally:
                completed()
                timer.deleteLater()

        timer.timeout.connect(poll)
        timer.start()

    buttons.accepted.connect(connect)
    buttons.rejected.connect(dialog.reject)
    dialog.finished.connect(finished)
    dialog.open()
    return dialog

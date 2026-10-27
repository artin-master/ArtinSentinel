"""Administrative transfer dialogs.

Inventory-only JSON remains supported. Credential-bearing transfers use an
authenticated encrypted .asx envelope and never write passwords in plaintext.
"""
import json,os,tempfile,sqlite3
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,
    QTreeWidget,QTreeWidgetItem,QTableWidget,QTableWidgetItem,QHeaderView,
    QDialogButtonBox,QPushButton,QFileDialog,QMessageBox,QInputDialog,QLineEdit)
from .access_control import authorize
from .config_portability import export_configuration,preview_configuration,import_configuration
from .secure_transfer import (
    SecureTransferError, collect_credentials, decrypt_bundle, encrypt_bundle,
    is_secure_bundle, restore_credentials,
)

MAX_FILE=12_000_000


def _note(text):
    label=QLabel(text);label.setWordWrap(True);return label


def _transfer_password(owner, title, *, confirm=False):
    first,ok=QInputDialog.getText(owner,title,'Senha de transferência:',QLineEdit.Password)
    if not ok:return None
    if len(first)<8:
        QMessageBox.warning(owner,title,'Use uma senha de transferência com pelo menos 8 caracteres.')
        return None
    if confirm:
        second,ok=QInputDialog.getText(owner,title,'Confirme a senha de transferência:',QLineEdit.Password)
        if not ok:return None
        if first!=second:
            QMessageBox.warning(owner,title,'As senhas de transferência não conferem.')
            return None
    return first


class ExportDevicesDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner
        self.setWindowTitle('Exportar equipamentos');self.resize(780,640)
        layout=QVBoxLayout(self)
        layout.addWidget(_note(
            'Escolha os equipamentos para levar a outro PC com o Sentinel. '
            'Sites sem equipamentos selecionados ficam fora do arquivo.'
        ))
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['Site / equipamento','Endereço','Fabricante / modelo'])
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet('QTreeWidget{alternate-background-color:#142333;}')
        layout.addWidget(self.tree,1)
        for site in owner.db.list_sites(include_archived=False):
            devices=owner.db.list_devices(site['id'])
            if not devices:continue
            parent=QTreeWidgetItem([site['name'],'',f'{len(devices)} equipamento(s)'])
            parent.setFlags(parent.flags()|Qt.ItemIsUserCheckable|Qt.ItemIsAutoTristate)
            self.tree.addTopLevelItem(parent)
            for device in devices:
                item=QTreeWidgetItem([device['name'],device['ip'],f"{device['manufacturer']} {device['model']}".strip()])
                item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setData(0,Qt.UserRole,int(device['id']))
                parent.addChild(item);item.setCheckState(0,Qt.Checked)
            parent.setExpanded(True)
        self.tree.header().setSectionResizeMode(0,QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2,QHeaderView.Stretch)
        row=QHBoxLayout();self.channels=QCheckBox('Canais');self.names=QCheckBox('Nomes e apelidos')
        self.streams=QCheckBox('Preferências de stream');self.layouts=QCheckBox('Layouts')
        for widget in (self.channels,self.names,self.streams,self.layouts):row.addWidget(widget)
        self.channels.setChecked(True);self.names.setChecked(True);self.streams.setChecked(True)
        layout.addLayout(row)
        def sync_channels(checked):
            self.streams.setEnabled(checked);self.layouts.setEnabled(checked)
        self.channels.toggled.connect(sync_channels)
        self.credentials=QCheckBox('Incluir credenciais salvas/sessão em pacote criptografado')
        self.credentials.setChecked(True)
        self.credentials.setToolTip(
            'Quando ativo, o arquivo inteiro é protegido por senha de transferência. '
            'As senhas dos DVRs não aparecem em texto aberto.'
        )
        layout.addWidget(self.credentials)
        layout.addWidget(_note(
            'Com credenciais: o Sentinel gera um arquivo .asx criptografado e pede uma única senha de transferência. '
            'Sem credenciais: gera o JSON tradicional, sem senhas/tokens.'
        ))
        self.summary=QLabel();layout.addWidget(self.summary)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText('Salvar arquivo…')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.tree.itemChanged.connect(self.update_summary);self.update_summary()

    def selected_ids(self):
        selected=set()
        for i in range(self.tree.topLevelItemCount()):
            parent=self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child=parent.child(j)
                if child.checkState(0)==Qt.Checked:selected.add(int(child.data(0,Qt.UserRole)))
        return selected

    def export_options(self):
        return dict(device_ids=self.selected_ids(),include_channels=self.channels.isChecked(),
            include_names=self.names.isChecked(),include_streams=self.channels.isChecked() and self.streams.isChecked(),
            include_layouts=self.channels.isChecked() and self.layouts.isChecked())

    def update_summary(self,*args):
        count=len(self.selected_ids());self.summary.setText(f'{count} equipamento(s) selecionado(s)')
        self.buttons.button(QDialogButtonBox.Save).setEnabled(count>0)


class ImportPreviewDialog(QDialog):
    def __init__(self,owner,payload,*,secure_credentials=False):
        super().__init__(owner);self.preview=preview_configuration(owner.db,payload)
        self.secure_credentials=bool(secure_credentials)
        self.setWindowTitle('Prévia da importação');self.resize(1000,610)
        layout=QVBoxLayout(self)
        layout.addWidget(_note(
            'Marque os novos equipamentos que deseja incluir. Cadastros já existentes e conflitos não são duplicados. '
            + ('Credenciais criptografadas também serão aplicadas aos cadastros compatíveis já existentes.' if self.secure_credentials else '')
        ))
        self.table=QTableWidget(len(self.preview['rows']),7)
        self.table.setHorizontalHeaderLabels(['Incluir','Situação','Site','Equipamento','Endereço','Canais','Motivo'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.setAlternatingRowColors(True)
        statuses={'new':('Novo','#7bd9b0'),'existing':('Já cadastrado','#9ab6c6'),'conflict':('Conflito','#e8b969')}
        for index,row in enumerate(self.preview['rows']):
            include=QTableWidgetItem();include.setData(Qt.UserRole,tuple(row['key']))
            include.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable if row['status']=='new' else Qt.ItemIsSelectable)
            include.setCheckState(Qt.Checked if row['status']=='new' else Qt.Unchecked)
            self.table.setItem(index,0,include)
            label,color=statuses[row['status']]
            values=[label,row['site'],row['name'],row['ip'],str(row['channels']),row['reason']]
            for column,text in enumerate(values,1):
                item=QTableWidgetItem(text);item.setToolTip(text)
                if column==1:item.setForeground(QColor(color))
                self.table.setItem(index,column,item)
        for column in range(6):self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.Stretch)
        layout.addWidget(self.table,1);self.summary=QLabel();layout.addWidget(self.summary)
        layout.addWidget(_note(
            'Layouts existentes ficam intactos. Senhas importadas são regravadas no cofre seguro deste computador; '
            'o arquivo de transferência não é usado como cofre permanente.'
            if self.secure_credentials else
            'Layouts existentes ficam intactos. Este arquivo não contém senhas; equipamentos novos serão validados no destino.'
        ))
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.table.itemChanged.connect(self.update_summary);self.update_summary()

    def selected_keys(self):
        return {tuple(self.table.item(row,0).data(Qt.UserRole)) for row in range(self.table.rowCount())
            if self.table.item(row,0).flags()&Qt.ItemIsUserCheckable and self.table.item(row,0).checkState()==Qt.Checked}

    def update_summary(self,*args):
        counts=self.preview['counts'];selected=len(self.selected_keys())
        suffix=' • credenciais compatíveis serão restauradas' if self.secure_credentials else ''
        self.summary.setText(
            f"Novos: {counts['new']} • Já cadastrados: {counts['existing']} • "
            f"Conflitos: {counts['conflict']} • Selecionados: {selected}{suffix}"
        )
        button=self.buttons.button(QDialogButtonBox.Ok)
        button.setText(f'Importar {selected} novo(s)' + (' + credenciais' if self.secure_credentials else ''))
        button.setEnabled(selected>0 or (self.secure_credentials and counts['existing']>0))


def _write_private_bytes(path,raw):
    if len(raw)>MAX_FILE:raise ValueError('O arquivo excede o limite seguro. Exporte menos equipamentos por vez.')
    fd,temporary=tempfile.mkstemp(prefix='.sentinel-transfer-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600);os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def _write_private(path,payload):
    """Backward-compatible inventory-only writer used by tests and legacy callers."""
    raw=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8')
    _write_private_bytes(Path(path),raw)


def export_devices(owner):
    if not authorize(owner,'admin'):return
    dialog=ExportDevicesDialog(owner)
    if dialog.exec()!=QDialog.Accepted or not authorize(owner,'admin'):return
    options=dialog.export_options()
    if not options['device_ids']:return
    include_credentials=dialog.credentials.isChecked()
    password=None
    if include_credentials:
        password=_transfer_password(owner,'Exportar equipamentos com credenciais',confirm=True)
        if password is None:return
        suggested='ArtinSentinel_equipamentos.asx'
        file_filter='Pacote seguro Sentinel (*.asx)'
    else:
        suggested='ArtinSentinel_equipamentos.json'
        file_filter='Inventário Sentinel (*.json)'
    path,_=QFileDialog.getSaveFileName(owner,'Exportar equipamentos',suggested,file_filter)
    if not path:return
    try:
        if not authorize(owner,'admin'):return
        payload=export_configuration(owner.db,**options)
        count=sum(len(site['devices']) for site in payload['sites'])
        if not count:raise ValueError('A seleção não contém mais equipamentos ativos. Reabra a exportação.')
        destination=Path(path)
        if include_credentials:
            credentials,missing=collect_credentials(owner,payload)
            if missing:
                answer=QMessageBox.question(
                    owner,'Credenciais incompletas',
                    f'{len(credentials)} equipamento(s) possuem credencial disponível e {len(missing)} não possuem.\n\n'
                    'Continuar e transportar somente as credenciais disponíveis?',
                    QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes,
                )
                if answer!=QMessageBox.Yes:return
            if destination.suffix.lower()!='.asx':destination=destination.with_name(destination.name+'.asx')
            raw=encrypt_bundle(payload,credentials,password)
        else:
            if destination.suffix.lower()!='.json':destination=destination.with_name(destination.name+'.json')
            raw=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8')
        if destination.exists() and QMessageBox.question(
            owner,'Substituir arquivo',f'{destination.name} já existe. Substituir?',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No
        )!=QMessageBox.Yes:return
        _write_private_bytes(destination,raw)
    except (OSError,ValueError,TypeError,OverflowError,sqlite3.Error,SecureTransferError) as exc:
        QMessageBox.warning(owner,'Exportar equipamentos',str(exc));return
    detail=(
        'Credenciais disponíveis foram protegidas por criptografia e poderão ser restauradas no outro Sentinel.'
        if include_credentials else
        'O arquivo foi gerado sem credenciais.'
    )
    QMessageBox.information(owner,'Equipamentos exportados',f"{count} equipamento(s) exportado(s).\n\n{detail}")


def import_devices(owner):
    if not authorize(owner,'admin'):return
    path,_=QFileDialog.getOpenFileName(
        owner,'Importar equipamentos','',
        'Pacote Sentinel (*.asx *.json);;Pacote seguro Sentinel (*.asx);;Inventário Sentinel (*.json)'
    )
    if not path:return
    credentials={}
    secure=False
    try:
        with Path(path).open('rb') as stream:raw=stream.read(MAX_FILE+1)
        if len(raw)>MAX_FILE:raise ValueError('Arquivo maior que o limite permitido.')
        if is_secure_bundle(raw):
            secure=True
            password=_transfer_password(owner,'Importar pacote criptografado',confirm=False)
            if password is None:return
            payload,credentials=decrypt_bundle(raw,password)
        else:
            payload=json.loads(raw.decode('utf-8-sig'))
        dialog=ImportPreviewDialog(owner,payload,secure_credentials=secure and bool(credentials))
    except (OSError,ValueError,TypeError,OverflowError,RecursionError,sqlite3.Error,SecureTransferError) as exc:
        QMessageBox.warning(owner,'Importar equipamentos',f'Não foi possível preparar a importação: {exc}');return
    if dialog.exec()!=QDialog.Accepted or not authorize(owner,'admin'):return
    try:
        counts=import_configuration(owner.db,payload,selected_keys=dialog.selected_keys(),expected_signature=dialog.preview['signature'])
        post_preview=preview_configuration(owner.db,payload)
        restored={'restored':0,'skipped':0}
        if secure and credentials:
            restored=restore_credentials(owner,payload,credentials,post_preview)
        from .import_onboarding import target_device_ids
        setup_ids=target_device_ids(post_preview)
        owner.refresh_all()
    except (ValueError,TypeError,OSError,OverflowError,sqlite3.Error,SecureTransferError) as exc:
        QMessageBox.warning(owner,'Importar equipamentos',str(exc));return
    skipped=dialog.preview['counts']
    credential_line=(
        f"\nCredenciais restauradas no cofre: {restored['restored']}."
        if secure else ''
    )
    QMessageBox.information(owner,'Importação concluída',
        f"Incluídos: {counts['devices']} equipamento(s), {counts['channels']} canal(is), {counts['sites']} Site(s) e {counts['layouts']} layout(s).\n"
        f"Preservados: {skipped['existing']} cadastro(s) existente(s). Conflitos ignorados: {skipped['conflict']}.{credential_line}\n\n"
        "O Sentinel validará acesso e canais apenas nos equipamentos que ainda estiverem pendentes.")
    if setup_ids and hasattr(owner,'begin_import_onboarding'):
        QTimer.singleShot(0,lambda ids=tuple(setup_ids):owner.begin_import_onboarding(ids))

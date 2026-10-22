"""Administrative transfer dialogs. Preview never changes the inventory."""
import json,os,tempfile,sqlite3
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,
    QTreeWidget,QTreeWidgetItem,QTableWidget,QTableWidgetItem,QHeaderView,
    QDialogButtonBox,QPushButton,QFileDialog,QMessageBox)
from .access_control import authorize
from .config_portability import export_configuration,preview_configuration,import_configuration

MAX_FILE=5_000_000


def _note(text):
    label=QLabel(text);label.setWordWrap(True);return label


class ExportDevicesDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner
        self.setWindowTitle('Exportar equipamentos');self.resize(760,600)
        layout=QVBoxLayout(self)
        layout.addWidget(_note('Escolha os equipamentos para levar a outro PC com o Sentinel. Sites sem equipamentos selecionados ficam fora do arquivo.'))
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
        layout.addWidget(_note('Identificação, endereço e portas acompanham os equipamentos. Senhas, tokens e rotas de vídeo não são exportados. Os canais precisarão ser validados no destino.'))
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
    def __init__(self,owner,payload):
        super().__init__(owner);self.preview=preview_configuration(owner.db,payload)
        self.setWindowTitle('Prévia da importação');self.resize(1000,590)
        layout=QVBoxLayout(self)
        layout.addWidget(_note('Marque os novos equipamentos que deseja incluir. Cadastros já existentes, arquivados e conflitos são preservados; não serão sobrescritos nem receberão canais adicionais.'))
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
        layout.addWidget(_note('Layouts existentes ficam intactos. Layouts ausentes usam somente os equipamentos novos selecionados. Nenhuma senha, configuração de usuário ou permissão é importada.'))
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.table.itemChanged.connect(self.update_summary);self.update_summary()

    def selected_keys(self):
        return {tuple(self.table.item(row,0).data(Qt.UserRole)) for row in range(self.table.rowCount())
            if self.table.item(row,0).flags()&Qt.ItemIsUserCheckable and self.table.item(row,0).checkState()==Qt.Checked}

    def update_summary(self,*args):
        counts=self.preview['counts'];selected=len(self.selected_keys())
        self.summary.setText(f"Novos: {counts['new']} • Já cadastrados: {counts['existing']} • Conflitos: {counts['conflict']} • Selecionados: {selected}")
        button=self.buttons.button(QDialogButtonBox.Ok);button.setText(f'Importar {selected} novo(s)');button.setEnabled(selected>0)


def _write_private(path,payload):
    raw=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8')
    if len(raw)>MAX_FILE:raise ValueError('O arquivo excede 5 MB. Exporte menos equipamentos por vez.')
    fd,temporary=tempfile.mkstemp(prefix='.sentinel-transfer-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600);os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def export_devices(owner):
    if not authorize(owner,'admin'):return
    dialog=ExportDevicesDialog(owner)
    if dialog.exec()!=QDialog.Accepted or not authorize(owner,'admin'):return
    options=dialog.export_options()
    if not options['device_ids']:return
    path,_=QFileDialog.getSaveFileName(owner,'Exportar equipamentos','ArtinSentinel_equipamentos.json','Inventário Sentinel (*.json)')
    if not path:return
    try:
        if not authorize(owner,'admin'):return
        payload=export_configuration(owner.db,**options)
        count=sum(len(site['devices']) for site in payload['sites'])
        if not count:raise ValueError('A seleção não contém mais equipamentos ativos. Reabra a exportação.')
        destination=Path(path)
        if destination.suffix.lower()!='.json':
            destination=destination.with_name(destination.name+'.json')
            if destination.exists() and QMessageBox.question(owner,'Substituir arquivo','O arquivo JSON já existe. Substituir?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        _write_private(destination,payload)
    except (OSError,ValueError,TypeError,OverflowError,sqlite3.Error) as exc:
        QMessageBox.warning(owner,'Exportar equipamentos',str(exc));return
    QMessageBox.information(owner,'Equipamentos exportados',f"{count} equipamento(s) exportado(s).\n\nO arquivo não contém senhas. No destino, importe o arquivo e valide as credenciais e os canais.")


def import_devices(owner):
    if not authorize(owner,'admin'):return
    path,_=QFileDialog.getOpenFileName(owner,'Importar equipamentos','','Inventário Sentinel (*.json)')
    if not path:return
    try:
        with Path(path).open('rb') as stream:raw=stream.read(MAX_FILE+1)
        if len(raw)>MAX_FILE:raise ValueError('Arquivo maior que 5 MB.')
        payload=json.loads(raw.decode('utf-8-sig'))
        dialog=ImportPreviewDialog(owner,payload)
    except (OSError,ValueError,TypeError,OverflowError,RecursionError,sqlite3.Error) as exc:
        QMessageBox.warning(owner,'Importar equipamentos',f'Não foi possível preparar a importação: {exc}');return
    if dialog.exec()!=QDialog.Accepted or not authorize(owner,'admin'):return
    try:
        counts=import_configuration(owner.db,payload,selected_keys=dialog.selected_keys(),expected_signature=dialog.preview['signature'])
        owner.refresh_all()
    except (ValueError,TypeError,OSError,OverflowError,sqlite3.Error) as exc:
        QMessageBox.warning(owner,'Importar equipamentos',str(exc));return
    skipped=dialog.preview['counts']
    QMessageBox.information(owner,'Importação concluída',
        f"Incluídos: {counts['devices']} equipamento(s), {counts['channels']} canal(is), {counts['sites']} Site(s) e {counts['layouts']} layout(s).\n"
        f"Preservados: {skipped['existing']} cadastro(s) existente(s). Conflitos ignorados: {skipped['conflict']}.\n\nInforme as credenciais e leia/valide os canais dos equipamentos importados.")

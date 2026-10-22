"""Manufacturer palette and model catalog; no network work in these dialogs."""
from dataclasses import replace
import sqlite3
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QBrush
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QLineEdit,QComboBox,QTreeWidget,QTreeWidgetItem,QSplitter,QTableWidget,QTableWidgetItem,
    QHeaderView,QDialogButtonBox,QColorDialog,QMessageBox,QPlainTextEdit)
from artin_akdb.brands import BrandRegistry,NEUTRAL
from .access_control import authorize
from .model_catalog import catalog_models,STATUS_LABELS
from .akdb import canonical_type_label
from .brand_tree import registry

class ManufacturersDialog(QDialog):
    def __init__(self,owner,brands=None):
        super().__init__(owner);self.owner=owner;self.brands=brands or registry()
        self.setWindowTitle('AKDB • Fabricantes e cores');self.resize(650,420)
        box=QVBoxLayout(self)
        note=QLabel('Preferências locais da AKDB. A cor identifica somente a marca, sem alterar nome amigável ou conexão.\nAliases não definem equivalência de protocolos ou de fabricantes OEM.')
        note.setWordWrap(True);box.addWidget(note)
        form=QFormLayout();self.choose=QComboBox();self.choose.addItem('Novo fabricante…',None)
        for p in self.brands.all():self.choose.addItem(p.name,p.id)
        self.name=QLineEdit();self.aliases=QLineEdit();self.aliases.setPlaceholderText('Separar nomes alternativos por vírgula')
        self.color=NEUTRAL;self.palette=QPushButton('Escolher cor…');self.palette.clicked.connect(self.pick_color)
        self.preview=QLabel();self.preview.setTextFormat(Qt.RichText)
        form.addRow('Fabricante',self.choose);form.addRow('Nome padronizado',self.name)
        form.addRow('Nomes alternativos',self.aliases);form.addRow('Cor da marca',self.palette);form.addRow('Prévia',self.preview)
        box.addLayout(form);self.error=QLabel(self.brands.warning);self.error.setWordWrap(True);box.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Salvar')
        buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);box.addWidget(buttons)
        self.choose.currentIndexChanged.connect(self.load);self.name.textChanged.connect(self.update_preview);self.load()

    def load(self):
        p=self.brands.profiles.get(self.choose.currentData())
        self.name.setText(p.name if p else '');self.aliases.setText(', '.join(p.aliases) if p else '')
        self.color=p.color if p else NEUTRAL;self.update_preview()

    def update_preview(self):
        from html import escape
        self.preview.setText('Nome amigável · <span style="color:'+self.color+'">'+escape(self.name.text() or 'Fabricante')+'</span>')
        self.palette.setText('Escolher cor… '+self.color)

    def pick_color(self):
        color=QColorDialog.getColor(QColor(self.color),self,'Cor do fabricante')
        if color.isValid():self.color=color.name().upper();self.update_preview()

    def save(self):
        if not authorize(self.owner,'admin'):return
        try:
            aliases=tuple(a.strip() for a in self.aliases.text().split(',') if a.strip())
            current=self.brands.profiles.get(self.choose.currentData())
            p=replace(current,name=self.name.text(),color=self.color,aliases=aliases) if current else self.brands.new(self.name.text(),self.color,aliases)
            self.brands.save(p)
        except (ValueError,OSError,sqlite3.Error,RuntimeError) as exc:
            self.error.setText(str(exc));return
        registry(reload=True)
        refresh=getattr(self.owner,'refresh_all',None)
        if refresh:refresh()
        for window in getattr(self.owner,'detached_windows',{}).values():window.refresh_sources()
        self.accept()

class ModelCatalogDialog(QDialog):
    def __init__(self,owner,rows=None):
        super().__init__(owner);self.setWindowTitle('AKDB • Catálogo de fabricantes e modelos');self.resize(1080,700)
        self.rows=catalog_models() if rows is None else rows
        box=QVBoxLayout(self);note=QLabel('Conhecimento de modelo não comprova recursos do aparelho instalado. Validação geral e validação por recurso são mostradas separadamente.')
        note.setWordWrap(True);box.addWidget(note)
        filters=QHBoxLayout();self.brand=QComboBox();self.brand.addItem('Todas as marcas','')
        for brand in sorted({r['manufacturer'] for r in self.rows}):self.brand.addItem(brand,brand)
        self.kind=QComboBox();self.kind.addItem('Todos os tipos','')
        for kind in sorted({r['type'] for r in self.rows}):self.kind.addItem(canonical_type_label(kind),kind)
        self.search=QLineEdit();self.search.setPlaceholderText('Pesquisar modelo, família ou protocolo…')
        filters.addWidget(self.brand);filters.addWidget(self.kind);filters.addWidget(self.search,1);box.addLayout(filters)
        split=QSplitter();self.tree=QTreeWidget();self.tree.setHeaderLabels(['Marca / tipo / modelo']);split.addWidget(self.tree)
        from PySide6.QtWidgets import QWidget
        detail=QWidget();right=QVBoxLayout(detail);self.heading=QLabel('Selecione um modelo');self.heading.setTextFormat(Qt.PlainText);self.heading.setWordWrap(True);right.addWidget(self.heading)
        self.features=QTableWidget(0,5);self.features.setHorizontalHeaderLabels(['Recurso','Estado','Firmware','Origem','Detalhes'])
        self.features.setEditTriggers(QTableWidget.NoEditTriggers)
        self.features.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for col,width in enumerate((155,180,140,115)):self.features.setColumnWidth(col,width)
        self.features.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch);right.addWidget(self.features,1)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);self.notes.setMaximumHeight(180);right.addWidget(self.notes)
        split.addWidget(detail);split.setSizes([300,780]);box.addWidget(split,1)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.button(QDialogButtonBox.Close).setText('Fechar');buttons.rejected.connect(self.reject);box.addWidget(buttons)
        self.tree.currentItemChanged.connect(self.show_model)
        self.brand.currentIndexChanged.connect(self.populate);self.kind.currentIndexChanged.connect(self.populate);self.search.textChanged.connect(self.populate)
        self.populate()

    def populate(self):
        self.tree.clear();self.features.setRowCount(0);self.notes.clear();self.heading.setText('Selecione um modelo')
        parents={};query=self.search.text().casefold();brands=registry()
        for row in self.rows:
            if self.brand.currentData() and row['manufacturer']!=self.brand.currentData():continue
            if self.kind.currentData() and row['type']!=self.kind.currentData():continue
            if query and query not in ' '.join((row['model'],row['family'],row['manufacturer'],*row['protocols'])).casefold():continue
            brand=row['manufacturer'];key=(brand,row['type'])
            if brand not in parents:
                parent=QTreeWidgetItem(self.tree,[brand]);parents[brand]=parent
                profile=brands.resolve(brand)
                if profile:parent.setForeground(0,QBrush(QColor(profile.color)))
            if key not in parents:parents[key]=QTreeWidgetItem(parents[brand],[canonical_type_label(row['type'])])
            item=QTreeWidgetItem(parents[key],[row['model']]);item.setData(0,Qt.UserRole,row)
        self.tree.expandAll()

    def show_model(self,item,*args):
        row=item.data(0,Qt.UserRole) if item else None
        self.features.setRowCount(0);self.notes.clear()
        if not row:self.heading.setText('Selecione um modelo');return
        general={'field-validated':'Validado em campo (geral)','documented':'Documentado','tested':'Testado (geral)','field-detected':'Detectado em campo','candidate':'Candidato','detected':'Detectado'}.get(row['general_status'],row['general_status'])
        self.heading.setText(f"{row['manufacturer']} • {row['model']} • {canonical_type_label(row['type'])}\nEstado geral do perfil: {general} • revisão {row['revision']}\n{row['id']}")
        self.features.setRowCount(len(row['features']))
        from .model_catalog import FEATURES
        for i,key in enumerate(FEATURES):
            feature=row['features'][key]
            source='AKDB • campo' if 'field' in feature['source'] else 'AKDB • documentação' if 'documentation' in feature['source'] else feature['source']
            values=(feature['label'],STATUS_LABELS[feature['status']],feature['firmware'],source,feature['detail'])
            for col,value in enumerate(values):
                cell=QTableWidgetItem(value);cell.setToolTip(feature['source'] if col==3 else value);self.features.setItem(i,col,cell)
        self.notes.setPlainText('Protocolos conhecidos: '+', '.join(row['protocols'])+'\nPortas candidatas: '+(', '.join(map(str,row['ports'])) or 'Não individualizadas')+'\nAplicativos relacionados: '+', '.join(row['domains'])+'\nOrigem: '+row['source']+'\n\n'+'\n'.join((*row['notes'],*row['negative_knowledge'])))

def open_manufacturers(owner):
    if authorize(owner,'admin'):ManufacturersDialog(owner).exec()

def open_catalog(owner):ModelCatalogDialog(owner).exec()

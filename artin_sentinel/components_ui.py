"""Component checks are off the Qt thread and do not connect to recorders."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QPushButton,QApplication,QHeaderView,QFileDialog
from .components import default_registry
from .media_observation import session_label

def open_components(owner):
    dialog=QDialog(owner);dialog.setWindowTitle('Componentes e SDKs');dialog.resize(1000,620)
    layout=QVBoxLayout(dialog)
    note=QLabel('Instalação, carregamento local e uso são estados distintos. A verificação não faz login nos DVRs.\nNovos componentes integrados ao Sentinel aparecem neste registro.');note.setWordWrap(True);layout.addWidget(note)
    table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Componente','Estado local','Versão','Detalhes'])
    table.setEditTriggers(QTableWidget.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
    table.setColumnWidth(0,205);table.setColumnWidth(1,155);table.setColumnWidth(2,170);layout.addWidget(table)
    active=QLabel();active.setWordWrap(True);layout.addWidget(active)
    row=QHBoxLayout();refresh=QPushButton('Verificar novamente');copy=QPushButton('Copiar diagnóstico');imp=QPushButton('Preparar suporte Hikvision…');close=QPushButton('Fechar')
    for b in (refresh,copy,imp,close):row.addWidget(b)
    layout.addLayout(row)
    state={'rows':[],'busy':False}
    def sessions():
        found=[]
        candidates=list(getattr(owner,'live_sessions',{}).values())+list(getattr(owner,'playback_sessions',{}).values())
        for window in getattr(owner,'detached_windows',{}).values():candidates.extend(window.sessions.values())
        single=getattr(owner,'playback_session',None)
        if single:candidates.append(single)
        for session in candidates:
            if hasattr(session,'url'):found.append(session_label(session)+' · '+str(session.current_state))
        active.setText('Sessões observadas neste painel: '+(' | '.join(found) if found else 'nenhuma sessão encontrada; presença local não comprova acesso ao DVR.'))
    def check():
        if state['busy']:return
        state['busy']=True;refresh.setEnabled(False);imp.setEnabled(False);note.setText('Verificando componentes locais… sem acessar DVRs.')
        future=owner.recorder_executor.submit(lambda:default_registry().inspect())
        def poll():
            if not future.done():QTimer.singleShot(100,poll);return
            try:state['rows']=future.result()
            except Exception:state['rows']=[dict(name='Verificação',state='Falhou',detail='Não foi possível concluir.')]
            table.setRowCount(len(state['rows']))
            for r,item in enumerate(state['rows']):
                for c,key in enumerate(('name','state','version','detail')):
                    cell=QTableWidgetItem(str(item.get(key,'—')));cell.setToolTip(cell.text());table.setItem(r,c,cell)
            state['busy']=False;refresh.setEnabled(True);imp.setEnabled(True);sessions();note.setText('Verificação local concluída. Carregamento OK não confirma login, imagem ou áudio do DVR.')
        QTimer.singleShot(100,poll)
    def import_hik():
        path=QFileDialog.getExistingDirectory(dialog,'Pasta extraída do SDK oficial Hikvision Linux x86_64')
        if not path:return
        from .hik_sdk import import_runtime
        state['busy']=True;refresh.setEnabled(False);imp.setEnabled(False);note.setText('Importando SDK para armazenamento persistente…')
        future=owner.recorder_executor.submit(import_runtime,path)
        def poll():
            if not future.done():QTimer.singleShot(100,poll);return
            try:future.result();note.setText('SDK importado. Ative o acesso no equipamento; o cadastro existente é preservado.')
            except Exception:note.setText('Importação falhou. Selecione a pasta extraída Linux x86_64 que contém libhcnetsdk.so.')
            state['busy']=False;refresh.setEnabled(True);imp.setEnabled(True)
        QTimer.singleShot(100,poll)
    def copied():
        sessions();QApplication.clipboard().setText('\n'.join(' | '.join(str(r.get(k,'—')) for k in ('name','state','version','detail')) for r in state['rows'])+'\n'+active.text())
    refresh.clicked.connect(check);copy.clicked.connect(copied);imp.clicked.connect(import_hik);close.clicked.connect(dialog.close)
    # Non-modal ownership keeps callbacks alive safely if the dialog is closed mid-check.
    owner._components_dialog=dialog;dialog.show();check()

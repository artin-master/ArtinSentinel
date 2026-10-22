"""Read-only, bounded, in-memory execution diagnostics; no shell execution."""
from collections import deque
from datetime import datetime
import re
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QCheckBox,QFileDialog,QApplication


class RuntimeLog:
    def __init__(self,limit=1000):self.lines=deque(maxlen=limit);self.version=0;self._noise_count=0
    def append(self,source,message):
        text=str(message or '')
        if 'Resumed reading at pts' in text:
            self._noise_count+=1
            if self._noise_count!=1:return
            text='FFmpeg: entrada abaixo da velocidade solicitada; avisos repetidos agrupados.'
        text=re.sub(r'(?:rtsp|rtsps|https?|dvrip|intelbras-[a-z]+)://\S+','<endereço omitido>',text,flags=re.I)
        text=re.sub(r'(?i)(authorization\s*:).*',r'\1 <omitido>',text)
        text=re.sub(r'(?i)\b(password|senha|serial|token)\s*[:=_]\s*[^\s,;]+',r'\1=<omitido>',text)
        text=re.sub(r'(?i)(-password\s+)\S+',r'\1<omitido>',text)
        for line in text.splitlines()[:10]:
            if line.strip():self.lines.append(f'{datetime.now():%H:%M:%S} [{source}] {line[:1000]}');self.version+=1
    def text(self):return '\n'.join(self.lines)+(f'\nAvisos repetidos de velocidade: {self._noise_count}' if self._noise_count else '')
    def clear(self):self.lines.clear();self._noise_count=0;self.version+=1


def record_runtime(owner,source,message):
    log=getattr(owner,'_runtime_log',None)
    if log is None:log=RuntimeLog();owner._runtime_log=log
    log.append(source,message)


def open_runtime_panel(owner):
    current=getattr(owner,'_runtime_panel',None)
    if current is not None:
        current.timer.start();current.poll();current.show();current.raise_();return
    if getattr(owner,'_runtime_log',None) is None:owner._runtime_log=RuntimeLog()
    panel=RuntimePanel(owner);owner._runtime_panel=panel;panel.show()


class RuntimePanel(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.log=owner._runtime_log;self.version=-1
        self.setWindowTitle('Painel técnico do Sentinel');self.resize(950,560)
        layout=QVBoxLayout(self)
        note=QLabel('Etapas e diagnósticos locais de Live View e Reprodução. Somente leitura; não executa comandos.\n'
                    'Histórico em memória limitado a 1.000 linhas; salvar é opcional. Endereços e credenciais são omitidos.')
        note.setWordWrap(True);layout.addWidget(note)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.text=QPlainTextEdit();self.text.setReadOnly(True);self.text.setMaximumBlockCount(1000);layout.addWidget(self.text)
        row=QHBoxLayout();self.paused=QCheckBox('Pausar visualização');row.addWidget(self.paused)
        copy=QPushButton('Copiar');copy.clicked.connect(lambda:QApplication.clipboard().setText(self.log.text()))
        save=QPushButton('Salvar diagnóstico…');save.clicked.connect(self.save)
        clear=QPushButton('Limpar');clear.clicked.connect(self.log.clear)
        close=QPushButton('Fechar');close.clicked.connect(self.reject)
        for button in (copy,save,clear,close):row.addWidget(button)
        layout.addLayout(row)
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.poll);self.timer.start();self.poll()
    def poll(self):
        if self.paused.isChecked():return
        sessions=list(getattr(self.owner,'playback_sessions',{}).values())
        single=getattr(self.owner,'playback_session',None)
        if single is not None and single not in sessions:sessions.append(single)
        states=[f"reprodução {i+1}: {s.current_state}, {s.frame_count} quadros" for i,s in enumerate(sessions)]
        self.summary.setText(' • '.join(states) if states else 'Nenhuma reprodução aberta neste momento.')
        if self.version!=self.log.version:
            self.version=self.log.version;self.text.setPlainText(self.log.text());self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())
    def save(self):
        path,_=QFileDialog.getSaveFileName(self,'Salvar diagnóstico','Sentinel_diagnostico.txt','Texto (*.txt)')
        if path:
            try:Path(path).write_text(self.log.text(),encoding='utf-8')
            except OSError:self.summary.setText('Não foi possível salvar no destino escolhido.')
    def done(self,result):self.timer.stop();super().done(result)

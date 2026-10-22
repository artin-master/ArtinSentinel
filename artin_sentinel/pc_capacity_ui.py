"""Thirty-second local measurement, non-modal and read-only."""
import json
import platform
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QProgressBar,QPlainTextEdit,QFileDialog
from .pc_capacity import PCSampler,PressureWarning,estimate_capacity


class PCMonitor:
    def __init__(self):
        self.sampler=PCSampler();self.warning=PressureWarning();self.samples=[]
        self.queue=queue.Queue();self.thread=None;self.latest=None;self.sequence=0
        self.recommended=None;self.reference_profiles=None
    def tick(self,sessions):
        alert=False
        while True:
            try:sample=self.queue.get_nowait()
            except queue.Empty:break
            if sample is not None:
                self.latest=sample;self.sequence+=1;self.samples.append((time.monotonic(),sample));self.samples=self.samples[-120:]
                pressure=dict(sample)
                if sample["profiles"]==self.reference_profiles: pressure["recommended"]=self.recommended
                alert=self.warning.update(pressure) or alert
        if self.thread is None or not self.thread.is_alive():
            def work():
                try:self.queue.put(self.sampler.sample(sessions))
                except (OSError,ValueError,RuntimeError):self.queue.put(None)
            self.thread=threading.Thread(target=work,name='pc-performance',daemon=True);self.thread.start()
        return alert


def monitor_for(owner):
    monitor=getattr(owner,'_pc_monitor',None)
    if monitor is None:monitor=PCMonitor();owner._pc_monitor=monitor
    return monitor


def open_pc_analysis(owner):
    current=getattr(owner,'_pc_analysis_dialog',None)
    if current is not None and current.isVisible():current.raise_();return
    dialog=PCAnalysisDialog(owner);owner._pc_analysis_dialog=dialog;dialog.show()


class PCAnalysisDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.monitor=monitor_for(owner)
        self.begin=time.monotonic();self.running=True;self.report=None;self.hardware={}
        self.setWindowTitle('Análise de desempenho deste PC');self.resize(700,470)
        layout=QVBoxLayout(self)
        text=QLabel('Mantenha as câmeras desejadas abertas por 30 segundos, sem trocar o perfil ou a quantidade.\n'
                    'O resultado estima a mistura medida; não é um limite garantido de câmeras.')
        text.setWordWrap(True);layout.addWidget(text)
        self.progress=QProgressBar();self.progress.setRange(0,30);layout.addWidget(self.progress)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);layout.addWidget(self.output)
        row=QHBoxLayout();self.cancel_button=QPushButton('Cancelar análise');self.cancel_button.clicked.connect(self.cancel)
        self.save_button=QPushButton('Salvar relatório…');self.save_button.setEnabled(False);self.save_button.clicked.connect(self.save)
        close=QPushButton('Fechar');close.clicked.connect(self.reject)
        for button in (self.cancel_button,self.save_button,close):row.addWidget(button)
        layout.addLayout(row)
        self.hardware_queue=queue.Queue()
        hardware_queue=self.hardware_queue
        def hardware():
            result={'sistema':platform.system(),'arquitetura':platform.machine(),'aceleracao_ffmpeg':[],'gpu':[]}
            try: result['distribuicao']=platform.freedesktop_os_release().get('PRETTY_NAME','Linux')
            except OSError: pass
            try:
                vendors={'0x8086':'Intel','0x10de':'NVIDIA','0x1002':'AMD'}
                result['gpu']=sorted(set(vendors.get(p.read_text().strip(),'fabricante não identificado') for p in Path('/sys/class/drm').glob('card[0-9]/device/vendor')))
                if shutil.which('ffmpeg'):
                    probe=subprocess.run(['ffmpeg','-hide_banner','-hwaccels'],capture_output=True,text=True,timeout=4)
                    result['aceleracao_ffmpeg']=probe.stdout.splitlines()[1:]
            except (OSError,subprocess.TimeoutExpired):pass
            hardware_queue.put(result)
        threading.Thread(target=hardware,name='pc-hardware',daemon=True).start()
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.poll);self.timer.start()
        self.output.setPlainText('Medindo CPU, memória e quadros recebidos… As câmeras continuam abertas.')

    def poll(self):
        if not self.running:return
        try:self.hardware=self.hardware_queue.get_nowait()
        except queue.Empty:pass
        elapsed=int(time.monotonic()-self.begin);self.progress.setValue(min(30,elapsed))
        sample=self.monitor.latest
        if sample:
            self.output.setPlainText(f"Câmeras: {sample['channels']}\nCPU do sistema: {sample['system_cpu']:.1f}%\n"
                                     f"CPU Sentinel e processos filhos: {sample['cpu']:.1f}% da capacidade total\n"
                                     f"RAM Sentinel/processos: {sample['rss_mb']} MiB • disponível: {sample['available_mb']} MiB\n"
                                     f"Quadros recebidos/alvo de exibição: {100*sample['fps_ratio']:.0f}%\n"
                                     f"Perfis: {', '.join(sample['profiles'])}\nTempo: {min(30,elapsed)}/30 s")
        if elapsed>=30:self.finish()

    def finish(self):
        self.running=False;self.timer.stop();self.cancel_button.setEnabled(False)
        samples=[sample for when,sample in self.monitor.samples if when>=self.begin]
        # Ignore only the first warm-up sample, never a later profile change.
        if samples and not samples[0]['stable']:samples=samples[1:]
        result=estimate_capacity(samples)
        self.report={'hardware':self.hardware,'medicao_segundos':30,'amostras':samples,'resultado':result,
                     'limites':'Sem credenciais, URLs ou nomes de câmeras. Aceleração anunciada pelo FFmpeg não significa uso ativo. Resolução/codec de origem não medidos neste diagnóstico.'}
        metrics=getattr(self.owner,'_ui_metrics',None)
        if metrics is not None: self.report['interface']=metrics.snapshot(since=self.begin)
        count=result['recommended']
        self.monitor.recommended=count
        self.monitor.reference_profiles=samples[-1]['profiles'] if samples else None
        title=(f"Estimativa: até {count} câmeras no mesmo perfil (medidas: {result['measured']})." if count is not None
               else 'Sem estimativa confiável de capacidade nesta medição.')
        self.output.appendPlainText('\n'+title+'\n'+result['note']+'\nAceleração disponível no FFmpeg: '+', '.join(self.hardware.get('aceleracao_ffmpeg',[]))+
                                    '\nGPU (fabricante): '+', '.join(self.hardware.get('gpu',[]))+'\nA disponibilidade de aceleração não confirma seu uso pelo Sentinel.')
        if metrics is not None:
            snapshot=self.report['interface']
            self.output.appendPlainText('\nInterface: atraso máximo da fila de eventos: '+str(snapshot['atraso_event_loop'].get('max_ms','—'))+' ms. Detalhes de Live/Reprodução no relatório.')
        self.save_button.setEnabled(True)

    def cancel(self):
        self.running=False;self.timer.stop();self.cancel_button.setEnabled(False)
        self.output.appendPlainText('\nAnálise cancelada. Nenhuma estimativa emitida. Câmeras preservadas.')

    def save(self):
        if not self.report:return
        path,_=QFileDialog.getSaveFileName(self,'Salvar análise de desempenho','Sentinel_desempenho_PC.json','JSON (*.json)')
        if path:
            try:Path(path).write_text(json.dumps(self.report,ensure_ascii=False,indent=2))
            except OSError:self.output.appendPlainText('Não foi possível salvar o relatório no destino escolhido.')

    def done(self,result):
        if self.running:self.cancel()
        super().done(result)

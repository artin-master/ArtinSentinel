"""Per-recorder SDK activation; optional persistent runtime import."""
import json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QCheckBox,QSpinBox,QLineEdit,
    QPushButton,QDialogButtonBox,QFileDialog,QMessageBox)
from .hik_sdk import settings,import_runtime,runtime_dir

class SDKDialog(QDialog):
    busy=False
    def reject(self):
        if not self.busy:super().reject()
    def closeEvent(self,event):
        if self.busy:event.ignore()
        else:super().closeEvent(event)

def configure(window,device_id=None,prefer_sdk=False):
    from .hik_recording import uses_hikvision_recordings
    device_id=device_id if device_id is not None else window.selected_device_id()
    device=window.db.get_device(device_id) if device_id else None
    if device is None or not uses_hikvision_recordings(device):
        QMessageBox.information(window,'Hikvision SDK local','Selecione um gravador Hikvision ou compatível no inventário.');return
    config=settings(device)
    dialog=SDKDialog(window);dialog.setWindowTitle('Hikvision • SDK local');dialog.resize(610,410)
    layout=QVBoxLayout(dialog)
    note=QLabel('Acesso opcional por SDK Linux. Main e pesquisa validados no DVR de teste; reprodução e exportação em validação.\n'
                'Cloud e áudio de escuta por este SDK ficam pendentes; aceleração até 8× exige teste físico. O acesso RTSP/ISAPI atual é mantido quando desativado.')
    note.setWordWrap(True);layout.addWidget(note)
    form=QFormLayout();enabled=QCheckBox('Usar SDK para pesquisa e reprodução deste equipamento')
    enabled.setChecked(config['enabled'] or prefer_sdk);form.addRow(enabled)
    live=QCheckBox('Usar também no Ao Vivo dos canais mapeados (Auto prefere Main)');live.setChecked(config['live'] or prefer_sdk);form.addRow(live)
    port=QSpinBox();port.setRange(1,65535);port.setValue(config['port']);form.addRow('Porta de serviço:',port)
    mapping=QLineEdit(', '.join(f'{a}={b}' for a,b in config['channels'].items()) or '1=1')
    mapping.setToolTip('Número no Sentinel = índice do SDK. Exemplo: 1=1, 17=33. Não inferimos canais IP automaticamente.')
    form.addRow('Mapa de canais:',mapping);layout.addLayout(form)
    help_label=QLabel('Somente canais explicitamente mapeados usam este SDK. Para a câmera analógica de teste, mantenha 1=1.\n'
                     'Substream será tentado apenas quando selecionado explicitamente; ainda não validado neste DVR.')
    help_label.setWordWrap(True);layout.addWidget(help_label)
    runtime=QLabel();runtime.setWordWrap(True)
    def status():
        try:runtime_dir();runtime.setText('Runtime persistente Hikvision disponível.')
        except ValueError:runtime.setText('Runtime ainda não importado. Selecione a pasta extraída do SDK oficial Linux x86_64.')
    status();layout.addWidget(runtime)
    importer=QPushButton('Importar pasta do SDK oficial…');layout.addWidget(importer)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);layout.addWidget(buttons)
    buttons.button(QDialogButtonBox.Save).setText('Salvar')
    buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
    def import_sdk():
        path=QFileDialog.getExistingDirectory(dialog,'Selecione a pasta do SDK Linux extraído')
        if not path:return
        dialog.busy=True;importer.setEnabled(False);buttons.setEnabled(False);runtime.setText('Importando runtime para armazenamento persistente…')
        future=window.recorder_executor.submit(import_runtime,path)
        def poll():
            if not future.done():QTimer.singleShot(100,poll);return
            try:future.result();status()
            except Exception:runtime.setText('Importação não concluída. Verifique a pasta e a arquitetura Linux x86_64.')
            dialog.busy=False;importer.setEnabled(True);buttons.setEnabled(True)
        QTimer.singleShot(100,poll)
    importer.clicked.connect(import_sdk)
    def save():
        try:
            channels={}
            for item in mapping.text().split(','):
                left,right=(int(value.strip()) for value in item.split('='))
                if not 1<=left<=256 or not 1<=right<=256 or str(left) in channels:raise ValueError()
                channels[str(left)]=right
            if enabled.isChecked():runtime_dir()
            window.db.merge_device_metadata(device_id,{'hik_sdk':dict(enabled=enabled.isChecked(),live=live.isChecked(),port=port.value(),channels=channels)})
        except (ValueError,TypeError):
            QMessageBox.warning(dialog,'SDK Hikvision','Confira o runtime e o mapa no formato 1=1, 17=33, com valores de 1 a 256.');return
        if hasattr(window,"clear_playback_results"):window.clear_playback_results()
        window._playback_loaded_device_id=None
        dialog.accept();window.refresh_playback_access();window.refresh_device_inspector()
        from .runtime_diagnostics import record_runtime
        record_runtime(window,'configuração','Hikvision: acesso '+('SDK local' if enabled.isChecked() else 'RTSP / ISAPI')+' salvo; refaça a pesquisa para trocar o backend dos resultados.')
        QMessageBox.information(window,'Acesso salvo','Configuração salva. Feche e reabra o canal. Na Reprodução, clique em Atualizar dia para pesquisar pelo acesso escolhido.')
    buttons.accepted.connect(save);buttons.rejected.connect(dialog.reject)
    dialog.exec()

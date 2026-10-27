"""Unified equipment add/edit dialog for Artin Sentinel."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .equipment_policy import access_policy
from .remote_access import ACCESS_CONNECTOR, ACCESS_LOCAL, ACCESS_PRIVATE, validate_recorder_host


@dataclass(slots=True)
class EquipmentEditorResult:
    name: str
    host: str
    manufacturer: str
    model: str
    kind: str
    provider: str
    connection_mode: str
    username: str
    password: str
    save_password: bool
    web_port: int
    rtsp_port: int
    sdk_port: int | None
    channel_limit: int
    use_intelbras_cloud: bool


class EquipmentEditorDialog(QDialog):
    """One surface for new, discovered and existing equipment."""

    def __init__(self, owner, *, device=None, discovered=None, site_name=""):
        super().__init__(owner)
        self.device=device
        self.discovered=discovered
        self.result_data: EquipmentEditorResult | None=None
        self.setWindowTitle("Equipamento — cadastro e acesso")
        self.resize(690, 690)

        root=QVBoxLayout(self)
        headline=QLabel("CADASTRO + ACESSO + VALIDAÇÃO")
        headline.setStyleSheet("font-weight:700;font-size:12px")
        root.addWidget(headline)
        desc=QLabel(
            "Preencha ou confirme a identificação. O Sentinel habilita somente os métodos compatíveis "
            "com a marca/tipo e, ao salvar, testa o acesso e lê os canais automaticamente."
        )
        desc.setWordWrap(True)
        root.addWidget(desc)

        form=QFormLayout()
        root.addLayout(form)

        self.site_label=QLabel(site_name or "Site atual")
        form.addRow("Site",self.site_label)

        def value(source,key,default=""):
            if source is None:return default
            try:return source[key] if hasattr(source,"keys") and key in source.keys() else getattr(source,key,default)
            except Exception:return default

        source=device if device is not None else discovered
        self.name=QLineEdit(str(value(source,"name","") or ""))
        self.host=QLineEdit(str(value(source,"ip","") or ""))
        self.manufacturer=QComboBox();self.manufacturer.setEditable(True)
        for item in ("Intelbras","Hikvision","Dahua","HiLook","JFL","Aitek","IT-Blue","MiboCam","Genérico / OEM"):
            self.manufacturer.addItem(item)
        maker=str(value(source,"manufacturer","") or "")
        if maker:
            idx=self.manufacturer.findText(maker,Qt.MatchFixedString)
            if idx>=0:self.manufacturer.setCurrentIndex(idx)
            else:self.manufacturer.setEditText(maker)
        self.model=QLineEdit(str(value(source,"model","") or ""))

        self.kind=QComboBox()
        for label,key in (
            ("DVR","dvr"),("NVR","nvr"),("DVR / Multi HD","xvr"),
            ("Câmera IP","camera"),("Não identificado","unknown"),
        ):
            self.kind.addItem(label,key)
        kind_value=str(value(source,"kind","unknown") or "unknown")
        self.kind.setCurrentIndex(max(0,self.kind.findData(kind_value)))

        form.addRow("Nome amigável",self.name)
        form.addRow("IP / host",self.host)
        form.addRow("Tipo",self.kind)
        form.addRow("Fabricante",self.manufacturer)
        form.addRow("Modelo",self.model)

        self.policy=QLabel()
        self.policy.setWordWrap(True)
        self.policy.setStyleSheet("color:#9bc8d5;font-size:11px;font-weight:600")
        form.addRow("Acesso detectado",self.policy)

        self.connection=QComboBox()
        self.connection.addItem("Rede local",ACCESS_LOCAL)
        self.connection.addItem("Rede privada / VPN",ACCESS_PRIVATE)
        self.connection.addItem("Conector por Site",ACCESS_CONNECTOR)
        self.cloud_option_index=self.connection.count()
        self.connection.addItem("Intelbras Cloud", "intelbras_cloud_bridge")
        form.addRow("Origem do acesso",self.connection)

        self.user=QLineEdit()
        self.user.setText(str(value(device,"credential_username","") or "admin"))
        self.password=QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Senha do equipamento")
        self.save_password=QCheckBox("Salvar no cofre seguro deste computador")
        self.save_password.setChecked(bool(value(device,"credential_saved",False)))
        form.addRow("Usuário",self.user)
        form.addRow("Senha",self.password)
        form.addRow("",self.save_password)

        self.web_port=QSpinBox();self.web_port.setRange(1,65535);self.web_port.setValue(80)
        self.rtsp_port=QSpinBox();self.rtsp_port.setRange(1,65535);self.rtsp_port.setValue(554)
        self.sdk_port=QSpinBox();self.sdk_port.setRange(1,65535);self.sdk_port.setValue(8000)
        self.sdk_label=QLabel("Porta SDK")
        self.channel_limit=QSpinBox();self.channel_limit.setRange(1,64);self.channel_limit.setValue(16)

        form.addRow("Porta Web",self.web_port)
        form.addRow("Porta RTSP",self.rtsp_port)
        self.sdk_row_widget=QWidget()
        sdkrow=QHBoxLayout(self.sdk_row_widget);sdkrow.setContentsMargins(0,0,0,0)
        sdkrow.addWidget(self.sdk_port);sdkrow.addStretch()
        form.addRow(self.sdk_label,self.sdk_row_widget)
        self.channel_label=QLabel("Canais a verificar")
        form.addRow(self.channel_label,self.channel_limit)

        self.access_state=QLabel("A validação ainda não foi executada.")
        self.access_state.setWordWrap(True)
        self.access_state.setStyleSheet("color:#9aaeb7;font-size:10px")
        form.addRow("Validação",self.access_state)

        self.manufacturer.currentTextChanged.connect(self._sync_policy)
        self.kind.currentIndexChanged.connect(self._sync_policy)
        self.connection.currentIndexChanged.connect(self._sync_policy)
        self._sync_policy()

        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.save_button=buttons.button(QDialogButtonBox.Save)
        self.save_button.setText("Salvar e validar acesso")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def set_saved_secret(self, username: str, password: str, *, saved: bool):
        self.user.setText(username or "admin")
        self.password.setText(password or "")
        self.save_password.setChecked(bool(saved))

    def _sync_policy(self):
        maker=self.manufacturer.currentText().strip()
        kind=str(self.kind.currentData() or "unknown")
        p=access_policy(maker,kind)
        self.policy.setText(p.description)
        cloud_allowed=p.allow_intelbras_cloud
        model=self.connection.model()
        item=model.item(self.cloud_option_index) if hasattr(model,"item") else None
        if item is not None:
            item.setEnabled(cloud_allowed)
        if not cloud_allowed and self.connection.currentData()=="intelbras_cloud_bridge":
            self.connection.setCurrentIndex(0)

        recorder=kind in {"dvr","nvr","xvr"}
        self.channel_limit.setEnabled(recorder)
        self.channel_label.setEnabled(recorder)
        self.sdk_port.setEnabled(bool(p.sdk_port and recorder))
        self.sdk_label.setEnabled(bool(p.sdk_port and recorder))
        if p.sdk_port:
            self.sdk_port.setValue(int(p.sdk_port))
        self.sdk_label.setText(
            "Porta HCNetSDK" if p.show_hik_sdk else
            "Porta NetSDK" if p.show_intelbras_sdk else
            "Porta SDK (não utilizada)"
        )
        cloud=self.connection.currentData()=="intelbras_cloud_bridge"
        for widget in (self.host,self.web_port,self.rtsp_port,self.sdk_port):
            widget.setEnabled(not cloud)
        if cloud:
            self.policy.setText("Intelbras Cloud selecionado. O Sentinel usará o fluxo Cloud homologado da marca.")

    def _accept(self):
        host=self.host.text().strip()
        cloud=self.connection.currentData()=="intelbras_cloud_bridge"
        if not cloud and not host:
            self.access_state.setText("Informe o IP/host antes de salvar.")
            self.host.setFocus()
            return
        if not cloud:
            try:
                validate_recorder_host(host)
            except ValueError as exc:
                self.access_state.setText(str(exc))
                self.host.setFocus()
                self.host.selectAll()
                return
        maker=self.manufacturer.currentText().strip()
        kind=str(self.kind.currentData() or "unknown")
        p=access_policy(maker,kind)
        password=self.password.text()
        if not cloud and not password:
            self.access_state.setText("Informe a senha para que o Sentinel valide o acesso e leia os canais agora.")
            self.password.setFocus()
            return
        self.result_data=EquipmentEditorResult(
            name=self.name.text().strip() or host or maker or "Equipamento",
            host=host,
            manufacturer=maker,
            model=self.model.text().strip(),
            kind=kind,
            provider=p.provider or "generic",
            connection_mode=str(self.connection.currentData() or ACCESS_LOCAL),
            username=self.user.text().strip() or "admin",
            password=password,
            save_password=self.save_password.isChecked(),
            web_port=self.web_port.value(),
            rtsp_port=self.rtsp_port.value(),
            sdk_port=self.sdk_port.value() if p.sdk_port else None,
            channel_limit=self.channel_limit.value(),
            use_intelbras_cloud=cloud,
        )
        self.accept()

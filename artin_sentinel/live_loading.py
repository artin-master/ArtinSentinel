"""Small, lazily allocated activity bar for a camera tile."""
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QProgressBar


class CameraLoadingBar(QProgressBar):
    def __init__(self,parent):
        super().__init__(parent)
        self.setRange(0,0);self.setTextVisible(False);self.setFixedHeight(5)
        self.setAccessibleName('Carregando imagem da câmera')
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet('QProgressBar {background:#294258; border:0; border-radius:2px;} QProgressBar::chunk {background:#37c8e8; border-radius:2px;}')
        parent.installEventFilter(self);self.reposition()

    def reposition(self):
        parent=self.parentWidget();width=max(1,min(180,parent.width()-32))
        self.setGeometry(max(0,(parent.width()-width)//2),max(0,parent.height()-18),width,5)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Resize,QEvent.Show):self.reposition()
        return super().eventFilter(watched,event)

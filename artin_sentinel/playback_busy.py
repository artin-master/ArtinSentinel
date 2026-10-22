"""Nonmodal search/opening activity indicator, owned by the playback workspace."""
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QFrame,QLabel,QProgressBar,QVBoxLayout,QWidget


class PlaybackBusyOverlay(QFrame):
    def __init__(self,parent):
        super().__init__(parent)
        self.setObjectName('playbackBusyOverlay')
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet('QFrame#playbackBusyOverlay {background:#142333; border:1px solid #37c8e8; border-radius:8px;} QLabel {color:#dce7f0; border:0; background:transparent;} QProgressBar {border:0; border-radius:3px; background:#0b1420; height:7px;} QProgressBar::chunk {background:#37c8e8;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(16,12,16,12);layout.setSpacing(8)
        self.label=QLabel();self.label.setWordWrap(True);layout.addWidget(self.label)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7);layout.addWidget(self.progress)
        parent.installEventFilter(self);self.hide()

    def reposition(self):
        parent=self.parentWidget()
        width=max(1,min(420,parent.width()-24))
        self.setFixedWidth(width)
        height=max(78,self.sizeHint().height())
        self.setGeometry(max(0,(parent.width()-width)//2),min(20,max(0,parent.height()-height)),width,min(height,parent.height()))

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Resize,QEvent.Show):self.reposition()
        return super().eventFilter(watched,event)


def refresh(owner):
    area=getattr(owner,'playback_video_grid',None)
    if not isinstance(area,QWidget):return None
    overlay=getattr(owner,'_day_search_overlay',None)
    day=getattr(owner,'_day_search_busy',False)
    video=getattr(owner,'_video_open_busy',False)
    if not day and not video:
        if overlay is not None:overlay.hide()
        return overlay
    if overlay is None:overlay=PlaybackBusyOverlay(area);owner._day_search_overlay=overlay
    if day:
        date=owner.playback_start.dateTime().toString('dd/MM/yyyy')
        text='Buscando gravações de '+date+'…'
        if getattr(owner,'_pending_day_search',False) and getattr(owner,'playback_search_worker',None) is not None:
            text='Aguardando consulta atual… Dia selecionado: '+date
    else:
        point=getattr(owner,'_video_open_point',None)
        text='Abrindo gravação'+(' das '+point.strftime('%H:%M:%S') if point is not None else '')+'…'
    overlay.label.setText(text);overlay.reposition();overlay.show();overlay.raise_()
    return overlay


def set_day_busy(owner,busy):
    owner._day_search_busy=bool(busy)
    return refresh(owner)


def set_video_busy(owner,busy,point=None):
    owner._video_open_busy=bool(busy)
    if point is not None:owner._video_open_point=point
    return refresh(owner)


def poll_video_busy(owner):
    if not getattr(owner,'_video_open_busy',False):return
    sessions=list(getattr(owner,'playback_sessions',{}).values())
    single=getattr(owner,'playback_session',None)
    if single is not None and single not in sessions:sessions.append(single)
    def ended(session):
        done=getattr(session,'_finished',None)
        return (done is not None and done.is_set()) or getattr(session,'current_state','') in {'unavailable','stopped','error','authentication'}
    if not sessions or any(getattr(s,'ever_had_frame',False) for s in sessions) or all(ended(s) for s in sessions):
        set_video_busy(owner,False)

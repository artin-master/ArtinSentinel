"""Day-first playback workspace. Backend clip bounds remain private implementation state."""
from .playback_busy import set_day_busy,set_video_busy,poll_video_busy
from PySide6.QtCore import QTime,QDateTime
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QPushButton,QVBoxLayout,QToolButton


def compact_playback(owner, layout, splitter, sidebar, side, stage, player,
                     timeline_label, clip_label, trim_row):
    owner._playback_day_mode = True
    bar=QWidget();row=QHBoxLayout(bar);row.setContentsMargins(0,0,0,0);row.setSpacing(6)
    # Move source controls out of the former sidebar; its table becomes optional.
    for widget in (owner.playback_device_combo,owner.playback_channel_combo,owner.playback_multi_check,owner.playback_start,owner.playback_search_btn):
        side.removeWidget(widget)
    while side.count():
        item=side.takeAt(0)
        if item.widget():item.widget().hide()
        elif item.layout():
            nested=item.layout()
            while nested.count():
                child=nested.takeAt(0)
                if child.widget():child.widget().hide()
    owner.playback_device_combo.setMinimumWidth(150);owner.playback_device_combo.setMaximumWidth(280)
    owner.playback_channel_combo.setMinimumWidth(100);owner.playback_channel_combo.setMaximumWidth(210)
    owner.playback_start.setDisplayFormat('dd/MM/yyyy');owner.playback_start.setMaximumWidth(145)
    owner.playback_start.setToolTip('Escolher dia e consultar disponibilidade das gravações')
    owner.playback_end.hide()
    start=owner.playback_start.dateTime();day=start.date()
    owner.playback_start.blockSignals(True);owner.playback_end.blockSignals(True)
    owner.playback_start.setDateTime(QDateTime(day,QTime(0,0)))
    owner.playback_end.setDateTime(QDateTime(day.addDays(1),QTime(0,0)))
    owner.playback_start.blockSignals(False);owner.playback_end.blockSignals(False)
    for text,widget in [('DVR',owner.playback_device_combo),('Canal',owner.playback_channel_combo),('Dia',owner.playback_start)]:
        row.addWidget(QLabel(text));row.addWidget(widget,1 if text=='DVR' else 0)
    owner.playback_search_btn.setText('Atualizar dia')
    row.addWidget(owner.playback_search_btn);row.addWidget(owner.playback_multi_check)
    owner.playback_details_button=QToolButton();owner.playback_details_button.setText('Trechos ▸')
    owner.playback_details_button.setCheckable(True)
    owner.playback_details_button.toggled.connect(sidebar.setVisible)
    owner.playback_details_button.toggled.connect(lambda checked:owner.playback_details_button.setText('Trechos ◂' if checked else 'Trechos ▸'))
    row.addWidget(owner.playback_details_button)
    layout.insertWidget(1,bar)
    sidebar.setMinimumWidth(280);side.setSpacing(5)
    side.addWidget(QLabel('TRECHOS DO DIA'))
    side.addWidget(owner.playback_channel_list)
    owner.playback_channel_list.hide()
    side.addWidget(owner.playback_results,1);owner.playback_results.show()
    owner.playback_results.setColumnWidth(2,65)
    player.addWidget(owner.playback_status);owner.playback_status.show()
    owner.playback_status.setMaximumHeight(36)
    owner.playback_status.setText('Escolha o DVR, canal e dia. A régua mostra as gravações disponíveis.')
    owner.playback_multi_check.toggled.connect(lambda checked:owner.playback_details_button.setChecked(True) if checked else None)
    splitter.insertWidget(0,stage);splitter.setStretchFactor(0,1);splitter.setStretchFactor(1,0)
    splitter.setSizes([1200,340]);sidebar.hide()
    player.setContentsMargins(8,6,8,6);player.setSpacing(4)
    for label in (timeline_label,clip_label):player.removeWidget(label);label.hide()
    owner.playback_hover_clock.setMaximumHeight(20)
    owner.playback_video_grid.setMinimumHeight(220)
    owner.playback_video_details.setText('Selecione o dia e clique na régua para reproduzir')
    owner.playback_screen.setText('Escolha um dia e clique em um horário com gravação')
    # Recorte/export details are available on demand; they never shrink the video by default.
    player.removeItem(trim_row)
    trim=QWidget();trim_layout=QVBoxLayout(trim);trim_layout.setContentsMargins(0,0,0,0);trim_layout.addLayout(trim_row)
    trim.hide()
    trim_toggle=QToolButton();trim_toggle.setText('Recorte ▾');trim_toggle.setCheckable(True)
    trim_toggle.toggled.connect(trim.setVisible)
    # Export button is in the main transport row; put the foldout beside it.
    for index in range(player.count()):
        sub=player.itemAt(index).layout()
        if sub is not None and sub.indexOf(owner.playback_export_btn)>=0:
            sub.insertWidget(sub.indexOf(owner.playback_export_btn),trim_toggle);break
    player.addWidget(trim)
    owner.playback_trim_panel=trim
    owner.set_playback_focus(None)


def queue_day_search(owner):
    """Read UI at execution time and coalesce repeated date/channel changes."""
    if getattr(owner,'_playback_day_mode',False):
        owner._pending_day_search=True
        set_day_busy(owner,True)
        owner.playback_day_search_timer.start()


def run_day_search(owner):
    if getattr(owner,'_closing_app',False):return
    if getattr(owner,'playback_search_worker',None) is not None:
        owner._pending_day_search=True;return
    owner._pending_day_search=False
    owner.search_playback_recordings()


def sync_day(owner,day):
    owner.playback_start.blockSignals(True);owner.playback_end.blockSignals(True)
    owner.playback_start.setDateTime(QDateTime(day,QTime(0,0)))
    owner.playback_end.setDateTime(QDateTime(day.addDays(1),QTime(0,0)))
    owner.playback_start.blockSignals(False);owner.playback_end.blockSignals(False)
    queue_day_search(owner)


def day_search_error(owner,error):
    owner._pending_day_search=False
    timer=getattr(owner,'playback_day_search_timer',None)
    if timer is not None:timer.stop()
    set_day_busy(owner,False)
    owner.playback_status.setText(error)

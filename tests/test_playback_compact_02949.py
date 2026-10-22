from types import SimpleNamespace
from PySide6.QtWidgets import QApplication,QWidget,QGridLayout,QLabel
from PySide6.QtGui import QImage,QColor
from artin_sentinel.app import MainWindow,PlaybackScreen

_APP=None

def test_single_playback_does_not_reserve_hidden_grid_cells():
    global _APP
    _APP=QApplication.instance() or QApplication([])
    parent=QWidget();grid=QGridLayout(parent);screens=[QLabel() for _ in range(4)]
    for i,s in enumerate(screens):grid.addWidget(s,i//2,i%2)
    host=SimpleNamespace(playback_screens=screens,playback_multi_check=SimpleNamespace(isChecked=lambda:False),playback_active_channels=[],playback_video_layout=grid)
    MainWindow.set_playback_focus(host,None)
    assert grid.rowStretch(0)==1 and grid.rowStretch(1)==0
    assert grid.columnStretch(0)==1 and grid.columnStretch(1)==0
    parent.close()


def test_playback_image_resizes_without_waiting_for_new_frame():
    global _APP
    _APP=QApplication.instance() or QApplication([])
    screen=PlaybackScreen(0,'');screen.resize(320,180);screen.show()
    image=QImage(160,90,QImage.Format_RGB888);image.fill(QColor('green'))
    screen.set_frame(image);screen.resize(640,360);_APP.processEvents()
    assert screen.pixmap().width()==640 and screen.pixmap().height()==360
    screen.setPixmap(__import__('PySide6.QtGui',fromlist=['QPixmap']).QPixmap());screen.resize(800,450);_APP.processEvents()
    assert screen.pixmap().isNull()
    screen.close()


def test_compact_playback_uses_day_and_optional_right_table():
    from PySide6.QtWidgets import QMainWindow,QStackedWidget
    import shiboken6
    global _APP
    _APP=QApplication.instance() or QApplication([])
    window=MainWindow.__new__(MainWindow);QMainWindow.__init__(window)
    window.pages=QStackedWidget();window.setCentralWidget(window.pages)
    window.playback_session=None;window.playback_audio_session=None;window.playback_sessions={};window.playback_active_channels=[]
    MainWindow.build_playback_page(window)
    window.resize(1400,900);window.show();_APP.processEvents()
    assert window.playback_start.displayFormat()=='dd/MM/yyyy'
    assert not window.playback_end.isVisible()
    assert not window.playback_results.isVisible()
    assert window.playback_video_grid.height()>450
    window.playback_details_button.setChecked(True);_APP.processEvents()
    assert window.playback_results.isVisible()
    assert window.playback_results.mapToGlobal(window.playback_results.rect().topLeft()).x()>window.playback_screen.mapToGlobal(window.playback_screen.rect().topLeft()).x()
    window.playback_poll_timer.stop();window.playback_day_search_timer.stop()
    shiboken6.delete(window)


def test_day_query_waits_for_previous_query_and_preserves_latest_request():
    from artin_sentinel.playback_layout import run_day_search
    calls=[];host=SimpleNamespace(playback_search_worker=object(),_pending_day_search=True,search_playback_recordings=lambda:calls.append(1))
    run_day_search(host)
    assert not calls and host._pending_day_search
    host.playback_search_worker=None;run_day_search(host)
    assert calls==[1] and not host._pending_day_search


def test_ui_measurement_records_slow_callback_and_keeps_return_value(monkeypatch):
    from artin_sentinel.ui_metrics import UiMetrics
    import artin_sentinel.ui_metrics as module
    clock=[10.0];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    metrics=UiMetrics();metrics.heartbeat();clock[0]=10.4;metrics.heartbeat()
    def callback():clock[0]+=.08;return 42
    assert metrics.run('playback',callback)==42
    snap=metrics.snapshot(since=10)
    assert snap['callbacks']['playback']['max_ms']==80
    assert snap['atraso_event_loop']['max_ms']==150


def test_day_keyboard_change_sets_whole_day_and_queues_search():
    from artin_sentinel.playback_layout import sync_day
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDateTimeEdit
    global _APP
    _APP=QApplication.instance() or QApplication([])
    queued=[];host=SimpleNamespace(playback_start=QDateTimeEdit(),playback_end=QDateTimeEdit(),_playback_day_mode=True,playback_day_search_timer=SimpleNamespace(start=lambda:queued.append(1)))
    sync_day(host,QDate(2026,10,5))
    assert host.playback_start.dateTime().toPython().isoformat()=='2026-10-05T00:00:00'
    assert host.playback_end.dateTime().toPython().isoformat()=='2026-10-06T00:00:00'
    assert queued


def test_configuration_actions_share_one_row():
    from PySide6.QtWidgets import QMainWindow,QStackedWidget,QPushButton
    import shiboken6
    global _APP
    _APP=QApplication.instance() or QApplication([])
    window=MainWindow.__new__(MainWindow);QMainWindow.__init__(window)
    window.pages=QStackedWidget();window.setCentralWidget(window.pages)
    window.build_devices_tab=lambda:None;window.build_akdb_tab=lambda:None;window.build_updates_tab=lambda:None
    window.build_configuration_page();window.resize(1400,900);window.show();_APP.processEvents()
    names=['Alterar senha','Analisar desempenho','Exportar equipamentos','Importar equipamentos']
    buttons=[next(b for b in window.findChildren(QPushButton) if b.text().startswith(name)) for name in names]
    positions=[b.mapToGlobal(b.rect().topLeft()).y() for b in buttons]
    assert len(set(positions))==1
    shiboken6.delete(window)


def test_failed_day_query_does_not_retry_pending_request():
    from artin_sentinel.playback_layout import day_search_error
    stopped=[];messages=[]
    host=SimpleNamespace(_pending_day_search=True,playback_day_search_timer=SimpleNamespace(stop=lambda:stopped.append(1)),playback_status=SimpleNamespace(setText=messages.append))
    day_search_error(host,'Conta sem acesso à busca (HTTP 401/403)')
    assert not host._pending_day_search and stopped and messages

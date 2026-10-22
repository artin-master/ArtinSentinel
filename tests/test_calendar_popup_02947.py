import pytest
import shiboken6

from datetime import date,datetime
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication,QWidget,QDateTimeEdit
from PySide6.QtCore import QDate,QDateTime,QTime,Qt,QPoint
from PySide6.QtTest import QTest
from artin_sentinel.recording_history_ui import RecordingHistoryDialog
from artin_sentinel.recording_history import DayCheck


_APP = None

@pytest.fixture(autouse=True)
def owned_widgets():
    # Keep the application alive and delete each test's widgets, including timers.
    global _APP
    _APP = QApplication.instance() or QApplication([])
    before = {id(widget) for widget in _APP.topLevelWidgets()}
    yield
    for widget in list(_APP.topLevelWidgets()):
        if id(widget) not in before and shiboken6.isValid(widget):
            shiboken6.delete(widget)


def test_date_edit_opens_history_instead_of_native_popup():
    from artin_sentinel.recording_history_ui import RecordingDateEdit
    app=QApplication.instance() or QApplication([])
    edit=RecordingDateEdit(QDateTime(QDate(2026,10,3),QTime(8,0)))
    edit.resize(240,32);edit.setCalendarPopup(True);edit.show()
    requests=[];edit.historyRequested.connect(lambda:requests.append(1))
    QTest.mouseClick(edit,Qt.LeftButton,pos=QPoint(edit.width()-8,15))
    assert requests==[1]
    assert edit.date()==QDate(2026,10,3)
    edit.close()


def test_auto_month_queries_only_unknown_days_and_schedules_after_busy(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.db=SimpleNamespace(path=tmp_path/'data.db');owner.playback_start=QDateTimeEdit()
    owner.playback_start.setDate(QDate(2026,9,3))
    dialog=RecordingHistoryDialog(owner,{'id':1},'http://example.invalid',('synthetic','synthetic'),1,automatic=True)
    calls=[];monkeypatch.setattr(dialog,'start',lambda days,oldest:calls.append((days,oldest)))
    dialog.cache.put(dialog.scope,DayCheck(date(2026,9,3),'recorded',datetime(2026,9,3,8)))
    dialog.query_visible_month()
    assert len(calls)==1 and len(calls[0][0])==29
    assert date(2026,9,3) not in calls[0][0]
    dialog.busy=True
    dialog.calendar.setCurrentPage(2026,8)
    dialog.query_visible_month()
    assert dialog.cancel_event.is_set() and dialog.pending_month
    dialog.busy=False;dialog.close();owner.close()


def test_latest_month_is_started_after_cancelled_scan_finishes(tmp_path,monkeypatch):
    from artin_sentinel.recording_history import HistoryResult
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.db=SimpleNamespace(path=tmp_path/'data.db');owner.playback_start=QDateTimeEdit()
    owner.playback_start.setDate(QDate(2026,9,3))
    dialog=RecordingHistoryDialog(owner,{'id':1},'http://example.invalid',('u','p'),1,automatic=True)
    dialog.month_debounce.stop();dialog.busy=True;dialog.pending_month=True
    dialog.messages.put(('result',HistoryResult((),None,False,True,date(2026,9,1),date(2026,9,30))))
    dialog.poll()
    assert not dialog.busy and not dialog.pending_month and dialog.month_debounce.isActive()
    dialog.close();owner.close()


def test_selecting_day_uses_whole_day_and_cancels_lookup(tmp_path):
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.db=SimpleNamespace(path=tmp_path/'data.db')
    owner.playback_start=QDateTimeEdit();owner.playback_end=QDateTimeEdit()
    owner.playback_start.setDate(QDate(2026,9,3))
    owner.playback_device_combo=SimpleNamespace(currentData=lambda:1)
    owner.selected_playback_channels=lambda:(1,)
    owner.playback_status=SimpleNamespace(setText=lambda _:None)
    dialog=RecordingHistoryDialog(owner,{'id':1},'http://example.invalid',('u','p'),1,automatic=True)
    dialog.busy=True;dialog.calendar.setSelectedDate(QDate(2026,9,7));dialog.use_day()
    assert owner.playback_start.dateTime().toPython()==datetime(2026,9,7)
    assert owner.playback_end.dateTime().toPython()==datetime(2026,9,8)
    assert dialog.cancel_event.is_set() and dialog.closing
    dialog.busy=False;owner.close()


def test_cancelled_network_query_does_not_mark_day_as_error():
    from threading import Event
    from artin_sentinel.recording_history import scan_days
    cancel=Event()
    def query(*args):cancel.set();raise RuntimeError('Busca cancelada')
    result=scan_days(query,1,[date(2026,10,1)],cancel_event=cancel)
    assert result.cancelled and result.days==()


def test_month_result_includes_cached_recorded_days(tmp_path):
    from artin_sentinel.recording_history import HistoryResult
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.db=SimpleNamespace(path=tmp_path/'data.db');owner.playback_start=QDateTimeEdit()
    owner.playback_start.setDate(QDate(2026,9,3))
    dialog=RecordingHistoryDialog(owner,{'id':1},'http://example.invalid',('u','p'),1,automatic=True)
    dialog.month_debounce.stop()
    dialog.cache.put(dialog.scope,DayCheck(date(2026,9,3),'recorded',datetime(2026,9,3,8)))
    dialog.messages.put(('result',HistoryResult((),None,True,False,date(2026,9,1),date(2026,9,30))))
    dialog.poll()
    assert '1 com gravação' in dialog.status.text()
    assert 'Nenhuma gravação' not in dialog.status.text()
    dialog.close();owner.close()


def test_date_click_loads_month_and_day_click_applies_range(tmp_path,monkeypatch):
    import time
    from PySide6.QtWidgets import QVBoxLayout,QLabel
    from artin_sentinel import recording_history_ui as ui
    from artin_sentinel.recording_history import scan_days
    from artin_sentinel.recording_search import Recording,SearchResult
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.db=SimpleNamespace(path=tmp_path/'data.db',get_device=lambda _: {'id':1})
    owner.playback_start=ui.RecordingDateEdit(QDateTime(QDate(2026,9,3),QTime(8,0)))
    owner.playback_end=ui.RecordingDateEdit(QDateTime(QDate(2026,9,3),QTime(9,0)))
    owner.playback_start.setCalendarPopup(True)
    owner.playback_device_combo=SimpleNamespace(currentData=lambda:1)
    owner.selected_playback_channels=lambda:(1,)
    owner._credentials_for_device=lambda _:('synthetic','synthetic')
    owner.playback_channel_endpoint=lambda *a:('http://example.invalid',554)
    owner.playback_status=QLabel();owner.search_playback_recordings=lambda:None
    layout=QVBoxLayout(owner);layout.addWidget(owner.playback_start);layout.addWidget(owner.playback_end)
    ui.add_history_controls(owner,layout)
    calls=[]
    def query(ch,begin,end):
        calls.append(begin.date())
        return SearchResult((Recording(ch,'2026-09-03 08:00:00','2026-09-03 09:00:00','Normal',10),)) if begin.day==3 else SearchResult(())
    def run(device,route,user,password,ch,days,**kwargs):return scan_days(query,ch,days,**kwargs)
    monkeypatch.setattr(ui,'run_history',run)
    owner.show();app.processEvents()
    QTest.mouseClick(owner.playback_start,Qt.LeftButton,pos=QPoint(owner.playback_start.width()-8,15))
    dialog=owner._recording_history_dialog
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
        if len(calls)==30 and not dialog.busy:break
    assert len(calls)==30 and not dialog.busy
    assert dialog.calendar.dateTextFormat(QDate(2026,9,3)).toolTip()=='Gravação encontrada'
    assert dialog.calendar.dateTextFormat(QDate(2026,9,4)).toolTip()=='Sem gravações na consulta completa'
    dialog.calendar.setSelectedDate(QDate(2026,9,3));dialog.calendar.clicked.emit(QDate(2026,9,3))
    assert owner.playback_start.dateTime().toPython()==datetime(2026,9,3)
    assert owner.playback_end.dateTime().toPython()==datetime(2026,9,4)
    assert not dialog.isVisible()
    owner.close()

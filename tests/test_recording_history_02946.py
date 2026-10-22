from datetime import date,datetime
import time,subprocess
from threading import Event
import pytest
import shiboken6
from PySide6.QtWidgets import QApplication
from test_intelbras_cloud_bridge_pilot import sdk,SERIAL,USER,PASSWORD


_APP = None

@pytest.fixture(autouse=True)
def owned_widgets():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    before = {id(widget) for widget in _APP.topLevelWidgets()}
    yield
    for widget in list(_APP.topLevelWidgets()):
        if id(widget) not in before and shiboken6.isValid(widget):
            shiboken6.delete(widget)


def test_burst_sdk_playback_is_paced_at_one_x(sdk,tmp_path,monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    from artin_sentinel.intelbras_cloud_recordings import playback_route
    payload=tmp_path/'burst.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=10','-t','8','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    route=playback_route('intelbras-cloud://127.0.0.1:55162/1?serial='+SERIAL,datetime(2026,10,19,8),datetime(2026,10,19,9))
    session=IntelbrasCloudLiveSession(route,USER,PASSWORD,sdk_dir=sdk,playback=True,fps=10)
    session.start()
    try:
        limit=time.monotonic()+2.5
        while time.monotonic()<limit:session.latest_frame();time.sleep(.02)
        assert 1<=session.frame_count<=35,session.frame_count
        assert session._thread.is_alive(),session.drain_diagnostics()
    finally:session.stop();assert session.wait_closed(5)


def test_history_keeps_empty_failure_partial_and_unknown_separate():
    from artin_sentinel.recording_history import scan_days
    from artin_sentinel.recording_search import SearchResult,Recording
    def query(channel,start,end):
        if start.day==1:return SearchResult(())
        if start.day==2:raise TimeoutError()
        if start.day==3:return SearchResult((),truncated=True)
        return SearchResult((Recording(channel,'2026-10-04 08:00:00','2026-10-04 09:00:00','Normal',10),))
    result=scan_days(query,1,[date(2026,10,n) for n in range(1,5)])
    assert [v.state for v in result.days]==['empty','error','partial','recorded']
    assert not result.verified and result.earliest==datetime(2026,10,4,8)


def test_oldest_checks_gaps_and_is_bounded_to_selected_range():
    from artin_sentinel.recording_history import scan_days
    from artin_sentinel.recording_search import SearchResult,Recording
    calls=[]
    def query(channel,start,end):
        calls.append(start.date())
        return SearchResult(()) if start.day<3 else SearchResult((Recording(channel,'2026-10-03 04:00:00','2026-10-03 05:00:00','Normal',10),))
    result=scan_days(query,1,[date(2026,10,n) for n in range(1,6)],oldest=True)
    assert result.earliest==datetime(2026,10,3,4) and result.verified
    assert calls==[date(2026,10,n) for n in range(1,4)]
    assert result.range_start==date(2026,10,1) and result.range_end==date(2026,10,5)


def test_history_cancel_preserves_completed_days():
    from artin_sentinel.recording_history import scan_days
    from artin_sentinel.recording_search import SearchResult
    cancel=Event()
    def query(*args):cancel.set();return SearchResult(())
    result=scan_days(query,1,[date(2026,10,1),date(2026,10,2)],cancel_event=cancel)
    assert result.cancelled and len(result.days)==1 and not result.verified


def test_history_cache_does_not_cross_device_channel_or_expose_credentials(tmp_path):
    from artin_sentinel.recording_history import HistoryCache,DayCheck
    path=tmp_path/'cache.json';cache=HistoryCache(path)
    entry=DayCheck(date(2026,10,1),'recorded',datetime(2026,10,1,8))
    cache.put('device-A/1',entry)
    restored=HistoryCache(path)
    assert restored.get('device-A/1',date(2026,10,1)).state=='recorded'
    assert restored.get('device-A/2',date(2026,10,1)) is None
    assert restored.get('device-B/1',date(2026,10,1)) is None


def test_calendar_day_selection_sets_exactly_one_day():
    from types import SimpleNamespace
    from PySide6.QtWidgets import QDateTimeEdit,QApplication
    from PySide6.QtCore import QDate
    from artin_sentinel.recording_history_ui import select_day
    app=QApplication.instance() or QApplication([])
    start=QDateTimeEdit();end=QDateTimeEdit()
    owner=SimpleNamespace(playback_start=start,playback_end=end)
    select_day(owner,QDate(2026,10,3))
    assert start.dateTime().toPython()==datetime(2026,10,3)
    assert end.dateTime().toPython()==datetime(2026,10,4)


def test_rejected_credentials_stop_history_without_retry():
    from artin_sentinel.recording_history import scan_days
    calls=[]
    def query(*args):
        calls.append(1);raise RuntimeError('Login recusado')
    result=scan_days(query,1,[date(2026,10,n) for n in range(1,5)])
    assert calls==[1] and not result.verified and result.days[0].state=='error'


def test_cloud_history_holds_one_lease_and_releases_on_cancel(monkeypatch):
    from artin_sentinel.recording_history import run_history
    from artin_sentinel.recording_search import SearchResult
    from types import SimpleNamespace
    from artin_sentinel import intelbras_wine,intelbras_cloud_recordings
    acquired=[];released=[];routes=[];cancel=Event()
    lease=SimpleNamespace(port=55001,release=lambda:released.append(1))
    def acquire(*args,**kwargs):acquired.append(args);return lease
    monkeypatch.setattr(intelbras_wine,'wine_manager',lambda:SimpleNamespace(acquire=acquire))
    def query(route,*args,**kwargs):
        routes.append(route);cancel.set();return SearchResult(())
    monkeypatch.setattr(intelbras_cloud_recordings,'search_cloud_recordings',query)
    result=run_history({},'intelbras-wine://127.0.0.1:37777/1?serial='+SERIAL,USER,PASSWORD,1,
                       [date(2026,10,1),date(2026,10,2)],cancel_event=cancel)
    assert len(acquired)==len(released)==len(routes)==1
    assert routes[0].startswith('intelbras-cloud://127.0.0.1:55001/') and result.cancelled


def test_calendar_paints_evidence_and_does_not_query_on_navigation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication,QWidget,QDateTimeEdit
    from PySide6.QtCore import QDate
    from artin_sentinel.recording_history_ui import RecordingHistoryDialog
    from artin_sentinel.recording_history import DayCheck
    app=QApplication.instance() or QApplication([])
    owner=QWidget();owner.db=SimpleNamespace(path=tmp_path/'data.db');owner.playback_start=QDateTimeEdit()
    owner.playback_start.setDate(QDate(2026,10,3))
    dialog=RecordingHistoryDialog(owner,{'id':1},'http://example.invalid',('user','secret'),1)
    try:
        dialog.cache.put(dialog.scope,DayCheck(date(2026,10,3),'recorded',datetime(2026,10,3,8)))
        dialog.paint_days()
        assert dialog.calendar.dateTextFormat(QDate(2026,10,3)).toolTip()=='Gravação encontrada'
        dialog.calendar.setCurrentPage(2026,9)
        assert not dialog.busy
        assert 'secret' not in dialog.cache.path.read_text()
        assert 'example.invalid' not in dialog.cache.path.read_text()
    finally:dialog.close();owner.close()


def test_partial_hit_cannot_prove_oldest_and_errors_are_bounded():
    from artin_sentinel.recording_history import scan_days
    from artin_sentinel.recording_search import SearchResult,Recording
    dates=[date(2026,10,n) for n in range(1,9)]
    result=scan_days(lambda *a:SearchResult((Recording(1,'2026-10-01 08:00:00','2026-10-01 09:00:00','Normal',1),),truncated=True),1,dates,oldest=True)
    assert result.earliest==datetime(2026,10,1,8) and not result.verified
    calls=[]
    def fail(*a):calls.append(1);raise TimeoutError()
    result=scan_days(fail,1,dates)
    assert len(calls)==3 and not result.verified


def test_cloud_speed_selector_preserves_enabled_acceleration(tmp_path):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication,QComboBox,QListWidget,QLabel,QPushButton
    from artin_sentinel.db import Database
    from artin_sentinel.app import MainWindow
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    app=QApplication.instance() or QApplication([])
    db=Database(tmp_path/'db');did=register_bridge_inventory(db,db.list_sites()[0]['id'],'Cloud',SERIAL,37777,4,managed=True)
    host=SimpleNamespace(db=db,playback_device_combo=QComboBox(),playback_channel_combo=QComboBox(),playback_channel_list=QListWidget(),playback_web_button=QPushButton(),playback_search_btn=QPushButton(),playback_access_note=QLabel(),playback_speed_combo=QComboBox(),clear_playback_results=lambda:None,_device_web_services=lambda _:[])
    host.playback_speed_combo.addItem('1×',1.0);host.playback_speed_combo.addItem('4×',4.0)
    host.playback_speed_combo.setCurrentIndex(1);host.playback_device_combo.addItem('Cloud',did)
    MainWindow.refresh_playback_channels(host)
    assert host.playback_speed_combo.isEnabled()
    assert host.playback_speed_combo.currentData()==4.0
    assert 'Velocidade' in host.playback_speed_combo.toolTip()
    db.close()

from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from artin_sentinel.app import RecordingTimeline

_APP=None

def ruler(channels=()):
    global _APP
    _APP=QApplication.instance() or QApplication([])
    widget=RecordingTimeline();widget.resize(1200,130)
    day=datetime(2026,10,20)
    widget.set_period(day,day+timedelta(days=1),[NS(start='2026-10-20 00:00:00',end='2026-10-21 00:00:00',channel=1)],channels)
    widget.show();_APP.processEvents()
    return widget

def wheel(widget,x,steps=1):
    event=QWheelEvent(QPointF(x,50),QPointF(x,50),QPoint(),QPoint(0,int(120*steps)),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
    QApplication.sendEvent(widget,event)

def test_wheel_zooms_around_pointer_without_seeking_or_changing_data():
    widget=ruler();chosen=[];widget.timeChosen.connect(chosen.append)
    try:
        x=widget._x(widget.start+timedelta(hours=9));anchor=widget.time_at(x)
        wheel(widget,x)
        assert (widget.view_end-widget.view_start).total_seconds()<86400
        assert abs((widget.time_at(x)-anchor).total_seconds())<.01
        assert widget.start==datetime(2026,10,20) and len(widget.recordings)==1
        assert not chosen
    finally:widget.close();widget.deleteLater();_APP.processEvents()

def test_scrollbar_moves_zoomed_window_and_click_chooses_correct_time():
    widget=ruler((1,2));chosen=[];widget.timeChosen.connect(chosen.append)
    try:
        wheel(widget,600,4)
        widget.view_scroll.setValue(widget.view_scroll.maximum())
        assert widget.view_end==widget.end
        marks=widget.five_minute_marks()
        assert marks and all(widget.view_start<=t<=widget.view_end for t in marks)
        point=widget.start+timedelta(hours=23,minutes=15)
        QTest.mouseClick(widget,Qt.LeftButton,pos=QPoint(widget._x(point),39))
        assert chosen==[point]
    finally:widget.close();widget.deleteLater();_APP.processEvents()

def test_reset_and_new_day_restore_full_period_without_playback():
    widget=ruler();chosen=[];widget.timeChosen.connect(chosen.append)
    try:
        wheel(widget,600,4)
        assert not widget.zoom_reset.isHidden()
        QTest.mouseClick(widget.zoom_reset,Qt.LeftButton)
        assert (widget.view_start,widget.view_end)==(widget.start,widget.end)
        assert not chosen
        wheel(widget,600,4)
        day=widget.start+timedelta(days=1);widget.set_period(day,day+timedelta(days=1))
        assert (widget.view_start,widget.view_end)==(widget.start,widget.end)
        assert widget.view_scroll.isHidden()
    finally:widget.close();widget.deleteLater();_APP.processEvents()

def test_zoom_limits_and_empty_period_are_safe():
    widget=ruler()
    try:
        for _ in range(30):wheel(widget,600)
        assert (widget.view_end-widget.view_start).total_seconds()==900
        wheel(widget,600,-8);wheel(widget,600,-8)
        assert (widget.view_start,widget.view_end)==(widget.start,widget.end)
        widget.set_period(None,None);wheel(widget,600)
        assert widget.time_at(600) is None
    finally:widget.close();widget.deleteLater();_APP.processEvents()

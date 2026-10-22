from datetime import datetime,timedelta
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from artin_sentinel.app import RecordingTimeline,MainWindow

_APP=None

def app():
    global _APP
    _APP=QApplication.instance() or QApplication([])
    return _APP


def test_day_ruler_has_five_minute_marks_and_exact_click():
    app();ruler=RecordingTimeline();ruler.resize(1800,82)
    start=datetime(2026,10,19);ruler.set_period(start,start+timedelta(days=1))
    ticks=ruler.five_minute_marks()
    assert len(ticks)==289 and ticks[1]==start+timedelta(minutes=5)
    points=[start+timedelta(hours=9,minutes=minute) for minute in (5,15)]
    chosen=[];ruler.timeChosen.connect(chosen.append)
    for point in points:
        QTest.mouseClick(ruler,Qt.LeftButton,pos=QPoint(ruler._x(point),39))
    assert chosen==points
    ruler.close();ruler.deleteLater();_APP.processEvents()


def test_ruler_keeps_precise_selection_between_marks_on_recorded_bar():
    app();ruler=RecordingTimeline();ruler.resize(1800,82)
    start=datetime(2026,10,19);ruler.set_period(start,start+timedelta(days=1))
    chosen=[];ruler.timeChosen.connect(chosen.append)
    x=ruler._x(start+timedelta(hours=9,minutes=7))
    QTest.mouseClick(ruler,Qt.LeftButton,pos=QPoint(x,50))
    assert chosen[0]==ruler.time_at(x)
    ruler.close();ruler.deleteLater();_APP.processEvents()


def test_playback_audio_errors_reach_technical_panel_without_video():
    app()
    audio=SimpleNamespace(latest_status=lambda:'Áudio gravado não confirmado',drain_diagnostics=lambda:['Stream map 0:a:0 matches no streams'])
    owner=SimpleNamespace(playback_audio_session=audio,playback_audio_status=QLabel(),playback_session=None)
    MainWindow.poll_playback_stream(owner)
    assert 'matches no streams' in owner._runtime_log.text()
    assert 'Áudio gravado não confirmado' in owner._runtime_log.text()
    owner.playback_audio_status.deleteLater();_APP.processEvents()

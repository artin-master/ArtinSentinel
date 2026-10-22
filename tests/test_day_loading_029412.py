from types import SimpleNamespace
from PySide6.QtWidgets import QApplication,QWidget,QLabel,QPushButton
from PySide6.QtCore import QDateTime
from artin_sentinel import playback_layout
from artin_sentinel.app import MainWindow

_APP=None

def host():
    global _APP
    _APP=QApplication.instance() or QApplication([])
    area=QWidget();area.resize(1000,500);area.show()
    return SimpleNamespace(playback_video_grid=area,playback_start=SimpleNamespace(dateTime=lambda:QDateTime.fromString('2026-10-19T00:00:00','yyyy-MM-ddTHH:mm:ss')))


def test_day_search_has_indeterminate_overlay_and_reuses_it_on_resize():
    owner=host()
    overlay=playback_layout.set_day_busy(owner,True)
    assert not overlay.isHidden() and overlay.progress.minimum()==overlay.progress.maximum()==0
    assert '19/10/2026' in overlay.label.text()
    area=owner.playback_video_grid;area.resize(700,300);_APP.processEvents()
    assert area.rect().contains(overlay.geometry())
    assert playback_layout.set_day_busy(owner,True) is overlay
    playback_layout.set_day_busy(owner,False)
    assert overlay.isHidden()
    area.close();area.deleteLater();_APP.processEvents()


def test_search_error_hides_overlay_and_cancels_pending_search():
    owner=host();playback_layout.set_day_busy(owner,True)
    owner._pending_day_search=True;owner.playback_status=QLabel()
    owner.playback_day_search_timer=SimpleNamespace(stop=lambda:None)
    playback_layout.day_search_error(owner,'Busca indisponível')
    assert owner._day_search_overlay.isHidden() and not owner._pending_day_search
    assert owner.playback_status.text()=='Busca indisponível'
    owner.playback_video_grid.close();owner.playback_video_grid.deleteLater();owner.playback_status.deleteLater();_APP.processEvents()


def test_worker_finished_hides_overlay_even_with_no_device():
    owner=host();playback_layout.set_day_busy(owner,True)
    owner._pending_day_search=False;owner.playback_search_worker=object()
    owner.playback_device_combo=SimpleNamespace(currentData=lambda:None)
    owner.playback_channel_combo=SimpleNamespace(count=lambda:0)
    owner.playback_search_btn=QPushButton()
    MainWindow.playback_search_finished(owner)
    assert owner.playback_search_worker is None and owner._day_search_overlay.isHidden()
    owner.playback_video_grid.close();owner.playback_video_grid.deleteLater();owner.playback_search_btn.deleteLater();_APP.processEvents()


def test_opening_recording_stays_busy_until_first_frame_or_failure():
    from datetime import datetime
    owner=host();session=SimpleNamespace(ever_had_frame=False,current_state='connecting')
    owner.playback_session=session;owner.playback_sessions={}
    playback_layout.set_video_busy(owner,True,datetime(2026,10,19,9,15))
    overlay=owner._day_search_overlay
    assert '09:15' in overlay.label.text() and not overlay.isHidden()
    playback_layout.poll_video_busy(owner);assert not overlay.isHidden()
    session.ever_had_frame=True;playback_layout.poll_video_busy(owner)
    assert overlay.isHidden()
    session.ever_had_frame=False
    playback_layout.set_video_busy(owner,True,datetime(2026,10,19,10,5))
    session.current_state='unavailable';playback_layout.poll_video_busy(owner)
    assert overlay.isHidden()
    owner.playback_video_grid.close();owner.playback_video_grid.deleteLater();_APP.processEvents()


def test_stopping_video_does_not_hide_pending_day_search():
    owner=host();playback_layout.set_day_busy(owner,True)
    playback_layout.set_video_busy(owner,False)
    assert not owner._day_search_overlay.isHidden()
    playback_layout.set_day_busy(owner,False);assert owner._day_search_overlay.isHidden()
    owner.playback_video_grid.close();owner.playback_video_grid.deleteLater();_APP.processEvents()


def test_previous_search_finishing_keeps_overlay_for_new_pending_day():
    owner=host();playback_layout.set_day_busy(owner,True)
    owner._playback_day_mode=True;owner._pending_day_search=True;owner.playback_search_worker=object()
    started=[];owner.playback_day_search_timer=SimpleNamespace(start=lambda:started.append(True))
    owner.playback_device_combo=SimpleNamespace(currentData=lambda:None)
    owner.playback_channel_combo=SimpleNamespace(count=lambda:0);owner.playback_search_btn=QPushButton()
    MainWindow.playback_search_finished(owner)
    assert started and not owner._day_search_overlay.isHidden()
    owner._pending_day_search=False;MainWindow.playback_search_finished(owner)
    assert owner._day_search_overlay.isHidden()
    owner.playback_video_grid.close();owner.playback_video_grid.deleteLater();owner.playback_search_btn.deleteLater();_APP.processEvents()

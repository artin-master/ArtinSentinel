from types import SimpleNamespace
from threading import Event
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from artin_sentinel.app import VideoTile

_APP=None

def tile(index=0):
    global _APP
    _APP=QApplication.instance() or QApplication([])
    widget=VideoTile(index);widget.resize(500,350);widget.show()
    widget.set_source('Câmera','Conectando…','RTSP',{'channel_id':index+1})
    _APP.processEvents()
    return widget


def cleanup(*widgets):
    for w in widgets:w.close();w.deleteLater()
    _APP.processEvents()


def test_first_frame_hides_own_loading_bar_without_affecting_other_camera():
    a,b=tile(),tile(1)
    assert a._loading_bar is None
    a.set_loading(True);b.set_loading(True)
    assert not a._loading_bar.isHidden()
    image=QImage(160,90,QImage.Format_RGB888);image.fill(QColor('green'))
    a.set_frame(image)
    assert a._loading_bar.isHidden() and not b._loading_bar.isHidden()
    assert a.body.pixmap() is not None and not a.body.pixmap().isNull()
    cleanup(a,b)


def test_reconnect_terminal_failure_and_clear_source_update_loading():
    t=tile();session=SimpleNamespace(current_state='connecting',_finished=Event())
    t.sync_loading(session);bar=t._loading_bar
    assert not bar.isHidden()
    session.current_state='playing';t.sync_loading(session);assert bar.isHidden()
    session.current_state='retrying';t.sync_loading(session);assert not bar.isHidden()
    assert t._loading_bar is bar
    session.current_state='unavailable';t.sync_loading(session);assert bar.isHidden()
    session.current_state='connecting';t.sync_loading(session);session._finished.set()
    t.sync_loading(session);assert bar.isHidden()
    t.set_loading(True);t.clear_source();assert bar.isHidden()
    cleanup(t)


def test_loading_bar_stays_inside_camera_on_resize():
    t=tile();t.set_loading(True);bar=t._loading_bar
    t.resize(260,180);_APP.processEvents()
    assert t.body.rect().contains(bar.geometry())
    assert bar.minimum()==bar.maximum()==0
    cleanup(t)


def test_loading_follows_source_when_tiles_are_swapped():
    a,b=tile(),tile(1);a.set_loading(True)
    a.swap_content_with(b)
    assert a._loading_bar.isHidden() and not b._loading_bar.isHidden()
    cleanup(a,b)

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication

from artin_sentinel.app import ZoomImageLabel


def test_inspector_zoom_buttons_are_removed_but_video_quadrant_zoom_remains():
    app = QApplication.instance() or QApplication([])
    source = open("artin_sentinel/app.py", encoding="utf-8").read()
    assert 'self.ptz_buttons["zoom-in"]' not in source
    assert 'self.ptz_buttons["zoom-out"]' not in source
    assert 'direction.startswith("zoom")' in source  # backend capability/movement stays intact

    body = ZoomImageLabel(0, "")
    body.setPixmap(QPixmap.fromImage(QImage(320, 180, QImage.Format.Format_RGB32)))
    event = QWheelEvent(
        QPointF(20, 20), QPointF(20, 20), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    body.wheelEvent(event)
    assert body.zoom_factor == 1.25
    assert event.isAccepted()
    app.processEvents()

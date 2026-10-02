from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

import artin_sentinel.app as app_module
from artin_sentinel.talkback import AudioInputPreferences


@pytest.fixture
def live_audio_controls(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    window = app_module.MainWindow.__new__(app_module.MainWindow)
    QMainWindow.__init__(window)
    window.live_audio_volume = 45
    window.live_audio_session = None
    window.audio_input_preferences = AudioInputPreferences()
    window.refresh_selected_audio_controls = Mock()
    monkeypatch.setattr(app_module, "data_dir", lambda: tmp_path)
    host = QWidget()
    window.setCentralWidget(host)
    layout = QVBoxLayout(host)
    window._build_live_audio_controls(layout)
    try:
        yield window, application
    finally:
        host.deleteLater()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_listening_percent_is_visible_and_updates_live(live_audio_controls):
    window, application = live_audio_controls
    assert window.audio_volume_value.text() == "45%"
    window.audio_volume_slider.setValue(63)
    application.processEvents()
    assert window.audio_volume_value.text() == "63%"
    assert window.live_audio_volume == 63


def test_microphone_percent_reset_and_independent_enable_state(live_audio_controls):
    window, application = live_audio_controls
    assert window.microphone_gain_value.text() == "100%"
    assert not window.microphone_gain_slider.isEnabled()
    assert not window.microphone_gain_reset_btn.isEnabled()
    window.set_microphone_gain_controls_enabled(True)
    assert window.microphone_gain_slider.isEnabled()
    assert window.microphone_gain_reset_btn.isEnabled()
    window.microphone_gain_slider.setValue(150)
    application.processEvents()
    assert window.microphone_gain_value.text() == "150%"
    QTest.mouseClick(window.microphone_gain_reset_btn, Qt.LeftButton)
    application.processEvents()
    assert window.microphone_gain_value.text() == "100%"
    assert window.audio_volume_slider.value() == 45


def test_listening_zero_is_muted_and_labels_are_clear(live_audio_controls):
    window, application = live_audio_controls
    labels = [label.text() for label in window.findChildren(app_module.QLabel)]
    assert "Áudio" in labels
    assert "Microfone" in labels
    assert window.microphone_test_btn.text() == "Testar"
    assert "MIC %:" not in labels
    window.audio_volume_slider.setValue(0)
    application.processEvents()
    assert window.audio_volume_value.text() == "0%"
    assert window.live_audio_volume == 0
    assert window.audio_volume_slider.minimum() == 0


@pytest.mark.parametrize("panel_width", [250, 285, 330])
def test_active_microphone_and_ptt_controls_stay_inside_narrow_inspector(
    live_audio_controls, panel_width,
):
    window, application = live_audio_controls
    panel = window.centralWidget()
    window.resize(panel_width, 420)
    window.show()
    window.microphone_row.show()
    window.talkback_btn.setText("PARAR")
    window.talkback_btn.show()
    window.netsdk_mode_label.show()
    window.netsdk_mode_combo.show()
    window.microphone_combo.setItemText(
        0, "Microfone USB PipeWire • dispositivo de captura Intelbras MiboCam instalado no balcão"
    )
    window.netsdk_mode_combo.setCurrentIndex(1)
    application.processEvents()

    controls = (
        window.audio_volume_slider, window.audio_volume_value, window.listen_audio_btn,
        window.talkback_btn, window.microphone_gain_slider, window.microphone_gain_value,
        window.microphone_gain_reset_btn, window.microphone_test_btn,
        window.microphone_combo, window.microphone_refresh_btn,
        window.netsdk_mode_label, window.netsdk_mode_combo,
    )
    for control in controls:
        control_name = control.objectName() or getattr(control, "text", lambda: "")()
        assert control.isVisible(), control_name
        left = control.mapTo(panel, control.rect().topLeft()).x()
        assert left >= 0
        assert left + control.width() <= panel.width(), (
            control_name, left, control.width(), panel.width()
        )

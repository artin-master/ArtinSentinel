import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow

import artin_sentinel.app as app
from artin_sentinel.media_process import wait_media_sessions


def test_shutdown_budget_is_shared_and_sessions_are_not_waited_twice(monkeypatch):
    now = [0.0]
    monkeypatch.setattr('time.monotonic', lambda: now[0])
    budgets = []
    def wait(seconds):
        budgets.append(seconds)
        now[0] += 2
        return True
    one = SimpleNamespace(wait_closed=wait, _process=None)
    two = SimpleNamespace(wait_closed=wait, _process=None)
    assert wait_media_sessions([one, one, None, two], timeout=3)
    assert budgets == [3, 1]


def test_shutdown_reaps_child_even_when_worker_did_not_finish():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    session = SimpleNamespace(wait_closed=lambda _: False, _process=child)
    try:
        assert not wait_media_sessions([session], timeout=0)
        assert child.poll() is not None
        assert child.stdout.closed and child.stderr.closed
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


@pytest.mark.parametrize('allow', [True, False])
def test_app_close_captures_media_before_maps_are_cleared_and_stops_timers(monkeypatch, allow):
    application = QApplication.instance() or QApplication([])
    w = app.MainWindow.__new__(app.MainWindow)
    QMainWindow.__init__(w)
    sessions = [Mock(_process=None) for _ in range(7)]
    for session in sessions:
        session.wait_closed.return_value = True
    w.live_sessions = {0: sessions[0]}
    w.live_audio_session, w.talkback_session = sessions[1:3]
    w.playback_session, w.playback_audio_session = sessions[3:5]
    w.playback_sessions = {0: sessions[3]}
    detached = SimpleNamespace(sessions={0: sessions[5]}, audio_session=sessions[6], close=Mock())
    w.detached_windows = {'window': detached}
    w.app_auth = Mock()
    w.manual_recording = w.playback_export_cancel = w.channel_scan_cancel_event = None
    w.db = Mock()
    for name in ('playback_poll_timer', 'channel_scan_poll_timer', 'live_poll_timer',
                 'ptz_poll_timer', 'monitor', 'performance_timer', 'discovery_clock',
                 'recorder_executor', 'ptz_executor', 'audio_executor'):
        setattr(w, name, Mock())
    monkeypatch.setattr(app, 'password_dialog', lambda *a, **kw: allow)
    monkeypatch.setattr(w, 'save_live_workspace', Mock())
    monkeypatch.setattr(w, 'stop_playback_stream', Mock())
    def stop_and_clear():
        for session in sessions:
            session.stop()
        w.live_sessions.clear()
        w.live_audio_session = w.talkback_session = None
    monkeypatch.setattr(w, 'stop_all_live_streams', stop_and_clear)
    event = QCloseEvent()
    app.MainWindow.closeEvent(w, event)
    try:
        if allow:
            assert event.isAccepted() and w._closing_app
            assert not w.live_sessions and not w.detached_windows
            for session in sessions:
                session.wait_closed.assert_called_once()
            w.performance_timer.stop.assert_called_once()
            w.discovery_clock.stop.assert_called_once()
            w.db.close.assert_called_once()
        else:
            assert not event.isAccepted()
            w.db.close.assert_not_called()
            for session in sessions:
                session.wait_closed.assert_not_called()
    finally:
        w.deleteLater()
        application.processEvents()

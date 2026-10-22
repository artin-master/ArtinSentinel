

def test_log_is_bounded_and_removes_secrets():
    from artin_sentinel.runtime_diagnostics import RuntimeLog
    log=RuntimeLog(limit=3)
    log.append('playback','rtsp://admin:secret@127.0.0.1/cam password=secret serial=ABC123')
    text=log.text()
    assert 'secret' not in text and 'admin' not in text and 'ABC123' not in text
    for i in range(10):log.append('playback',f'frame {i}')
    assert len(log.lines)==3


def test_flow_events_remain_available_after_first_frame():
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    from types import SimpleNamespace
    session=IntelbrasCloudLiveSession('intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE&start=2026-10-19T08:00:00&end=2026-10-19T09:00:00','TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',playback=True)
    events=[dict(stage='playback_flow_paused',buffered=20000,queued=1100),dict(stage='playback_flow_resumed',buffered=5000,queued=100),dict(stage='stream_error',reason='buffer_capacity')]
    session._handle_events(SimpleNamespace(poll_events=lambda:events,events=events))
    text=' '.join(session.drain_diagnostics())
    assert '1100' in text and 'buffer_capacity' in text and 'retomado' in text


_APP=None

def test_panel_reuses_window_and_stops_timer_on_close(tmp_path):
    from PySide6.QtWidgets import QApplication,QWidget
    from artin_sentinel.runtime_diagnostics import record_runtime,open_runtime_panel
    global _APP
    _APP=QApplication.instance() or QApplication([])
    owner=QWidget()
    record_runtime(owner,'reprodução','fluxo pausado para drenar • fila 1100 pacotes')
    open_runtime_panel(owner);panel=owner._runtime_panel
    assert panel.text.isReadOnly() and '1100' in panel.text.toPlainText()
    panel.reject();assert not panel.timer.isActive()
    record_runtime(owner,'reprodução','fluxo retomado')
    open_runtime_panel(owner)
    assert owner._runtime_panel is panel and panel.timer.isActive()
    assert 'retomado' in panel.text.toPlainText()
    panel.grab().save(str(tmp_path/'panel.png'))
    panel.reject();owner.close();owner.deleteLater();_APP.processEvents()

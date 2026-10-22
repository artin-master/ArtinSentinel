import io
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import artin_sentinel.talkback as talk

TYPES = [talk.XmDvripTalkbackSession, talk.IntelbrasHttpTalkbackSession,
         talk.IntelbrasNetSDKTalkbackSession]


@pytest.mark.parametrize('kind', TYPES)
def test_stop_before_start_cannot_open_microphone_or_transport(kind, monkeypatch):
    session = kind('192.0.2.1', 'admin', 'secret')
    thread = Mock()
    monkeypatch.setattr(talk.threading, 'Thread', thread)
    session.stop()
    session.stop()
    session.start()
    thread.assert_not_called()
    assert session.finished


@pytest.mark.parametrize('kind', TYPES)
def test_capture_opened_after_stop_is_reaped_without_publication(kind):
    session = kind('192.0.2.1', 'admin', 'secret')
    session.stop()
    child = Mock()
    child.poll.return_value = None
    child.wait.side_effect = lambda **kw: setattr(child.poll, 'return_value', 0)
    child.stdout = io.BytesIO()
    child.stderr = io.BytesIO()
    child.stdin = None
    assert not session._adopt_capture(child)
    assert child.poll() == 0 and child.stdout.closed
    assert session._process is None


@pytest.mark.parametrize('kind', TYPES)
def test_active_capture_stop_is_idempotent_and_worker_reaps_child(kind, monkeypatch):
    session = kind('192.0.2.1', 'admin', 'secret')
    entered = threading.Event()
    children = []
    def run():
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        children.append(child)
        session._adopt_capture(child)
        entered.set()
        session._stop.wait(2)
    monkeypatch.setattr(session, '_run', run)
    session.start()
    assert entered.wait(2)
    worker = session._thread
    session.start()
    assert session._thread is worker
    session.stop()
    session.stop()
    assert session.wait_closed(2)
    worker.join(1)
    assert not worker.is_alive()
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed and session._process is None


@pytest.mark.parametrize('kind', TYPES)
def test_transport_error_is_sanitized_and_finishes_session(kind, monkeypatch):
    session = kind('192.0.2.1', 'admin', 'secret')
    monkeypatch.setattr(session, '_run', Mock(side_effect=OSError('admin secret password=hidden')))
    session._run_wrapper()
    assert session.finished and session._process is None
    text = ' '.join(session.drain_diagnostics())
    assert 'admin' not in text and 'secret' not in text and 'hidden' not in text
    assert 'OSError' in text


def test_http_connection_returned_after_cancel_is_closed_before_capture(monkeypatch):
    session = talk.IntelbrasHttpTalkbackSession('192.0.2.1', 'admin', 'secret')
    connection = Mock()
    def open_connection(*args, **kwargs):
        session.stop()
        return connection, 'digest', '', 0, ''
    monkeypatch.setattr(talk, '_open_intelbras_postaudio_stream', open_connection)
    with pytest.raises(InterruptedError):
        session._run_framing_attempt('singlepart', [('pulse', ['ffmpeg'])])
    connection.close.assert_called_once()
    assert session._connection is None and session._process is None


def test_http_stop_interrupts_socket_and_still_closes_connection():
    session = talk.IntelbrasHttpTalkbackSession('192.0.2.1', 'admin', 'secret')
    session._connection = Mock()
    session._connection.sock.shutdown.side_effect = OSError('closed')
    session.stop()
    session._connection.close.assert_called_once()


def test_dvrip_stop_during_claim_does_not_start_talk_or_capture(monkeypatch):
    session = talk.XmDvripTalkbackSession('192.0.2.1', 'admin', 'secret')
    control, data = Mock(), Mock()
    control.session = 1
    data.sequence = 1
    context = Mock()
    context.__enter__ = Mock(return_value=control)
    context.__exit__ = Mock(return_value=False)
    data.talk_claim.side_effect = session.stop
    created = iter([context, data])
    monkeypatch.setattr(talk, 'DvripSession', lambda *a, **kw: next(created))
    monkeypatch.setattr(session, '_capture_commands', lambda: [('pulse', ['ffmpeg'])])
    session._run_wrapper()
    control.talk_start_no_reply.assert_not_called()
    data.close.assert_called_once()
    assert session.finished and session._talk_session is None


def test_netsdk_stop_during_login_logs_out_without_starting_talk(monkeypatch):
    session = talk.IntelbrasNetSDKTalkbackSession('192.0.2.1', 'admin', 'secret',
                                               test_mode='live-pcm-literal')
    sdk = Mock()
    def login(*args):
        session.stop()
        return SimpleNamespace(handle=10, port=37777, channels=1)
    sdk.login.side_effect = login
    monkeypatch.setattr(talk, 'netsdk_runtime_info', lambda: SimpleNamespace(available=True, architecture='x86_64'))
    monkeypatch.setattr(talk, 'IntelbrasNetSDK', SimpleNamespace(instance=lambda: sdk))
    monkeypatch.setattr(session, '_capture_commands', lambda *a: [('pulse', ['ffmpeg'])])
    session._run_wrapper()
    sdk.logout.assert_called_once_with(10)
    sdk.configure_direct_talk.assert_not_called()
    sdk.lib.CLIENT_StartTalkEx.assert_not_called()
    assert session.finished and session._login_handle == 0


def test_netsdk_cleanup_stops_original_handles_once():
    session = talk.IntelbrasNetSDKTalkbackSession('192.0.2.1', 'admin', 'secret')
    sdk = Mock()
    session._sdk = sdk
    session._talk_handle, session._login_handle = 20, 10
    session._cleanup()
    session._cleanup()
    sdk.lib.CLIENT_StopTalkEx.assert_called_once_with(20)
    sdk.logout.assert_called_once_with(10)

import io
import subprocess
import sys
import threading
from unittest.mock import Mock

import pytest
import artin_sentinel.live as live
from artin_sentinel.media_process import terminate_media_process


def process():
    p = Mock()
    p.poll.return_value = None
    p.wait.side_effect = lambda **kw: setattr(p.poll, "return_value", 0)
    p.stdout = io.BytesIO()
    p.stderr = io.BytesIO()
    p.stdin = None
    return p


def test_stop_during_popen_reaps_late_child_without_publishing_or_reading(monkeypatch):
    session = live.LiveStreamSession('rtsp://camera/main')
    child = process()
    monkeypatch.setattr(session, '_command', lambda *args: ['unused'])
    def spawn(*args, **kwargs):
        session.stop()
        return child
    monkeypatch.setattr(live.subprocess, 'Popen', spawn)
    assert not session._attempt_profile(session.url, 'Main')
    assert session._process is None
    assert session.current_state == 'stopped'
    child.terminate.assert_called_once()
    assert child.poll() == 0
    assert child.stdout.closed


def test_closed_session_cannot_start_or_publish_late_frame(monkeypatch):
    session = live.LiveStreamSession('rtsp://camera/main')
    session.stop()
    start = Mock()
    monkeypatch.setattr(live.threading, 'Thread', start)
    session.start()
    session._push_frame(live.FramePacket(b'late'))
    assert session.latest_frame() is None
    start.assert_not_called()
    assert session.finished


def test_start_is_idempotent_while_worker_running(monkeypatch):
    session = live.LiveStreamSession('rtsp://camera/main')
    entered = threading.Event()
    monkeypatch.setattr(session, '_run', lambda: (entered.set(), session._stop.wait(2)))
    session.start()
    assert entered.wait(1)
    thread = session._thread
    session.start()
    assert session._thread is thread
    session.stop()
    assert session.wait_closed(1)
    assert not thread.is_alive()


def test_reaper_kills_waits_and_closes_pipes_when_terminate_times_out():
    child = process()
    child.wait.side_effect = [subprocess.TimeoutExpired('child', 0.01), 0]
    terminate_media_process(child, grace=0.01)
    child.kill.assert_called_once()
    assert child.wait.call_count == 2
    assert child.stdout.closed and child.stderr.closed


def test_stop_reaps_real_media_child_and_repeated_stop_is_safe():
    session = live.LiveStreamSession('rtsp://camera/main')
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert session._adopt_process(child)
        session.stop()
        session.stop()
        assert child.poll() is not None
        assert child.stdout.closed and child.stderr.closed
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_backoff_is_bounded_resets_on_frame_and_close_cancels_retry(monkeypatch):
    session = live.LiveStreamSession('rtsp://camera/main')
    monkeypatch.setattr(live.shutil, 'which', lambda _: '/ffmpeg')
    results = iter([False] * 8 + [True, False])
    attempts, waits = [], []
    def attempt(*args):
        attempts.append(args)
        got = next(results)
        session.ever_had_frame |= got
        return got
    def wait(delay):
        waits.append(delay)
        if len(waits) == 10:
            session.stop()
        return session._stop.is_set()
    monkeypatch.setattr(session, '_attempt_profile', attempt)
    monkeypatch.setattr(session._stop, 'wait', wait)
    session._run()
    assert waits == [2, 2, 2, 5, 5, 5, 30, 30, 2, 2]
    assert len(attempts) == 10
    session._run()
    assert len(attempts) == 10


def test_authentication_rejection_does_not_try_udp_or_main_sub_loop(monkeypatch):
    session = live.LiveStreamSession('rtsp://camera/main', fallback_url='rtsp://camera/sub',
                                     transport_fallback=True)
    monkeypatch.setattr(live.shutil, 'which', lambda _: '/ffmpeg')
    calls = []
    def attempt(*args):
        calls.append(args)
        session._stderr_reader(io.BytesIO(b'RTSP server returned 401 Unauthorized\n'), 'Main')
        return False
    monkeypatch.setattr(session, '_attempt_profile', attempt)
    session._run()
    assert len(calls) == 1
    assert session.current_state == 'authentication'
    assert 'autenticação' in session.latest_status()


def test_wrapper_always_finishes_on_decoder_exception(monkeypatch):
    session = live.LiveStreamSession('rtsp://camera/main')
    monkeypatch.setattr(session, '_run', Mock(side_effect=ValueError('invalid')))
    session._run_wrapper()
    assert session.current_state == "unavailable"
    assert "ValueError" in " ".join(session.drain_diagnostics())
    assert session.finished
    assert session._process is None

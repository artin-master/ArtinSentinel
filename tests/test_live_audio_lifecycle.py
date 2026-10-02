import io
import subprocess
import sys
import threading
from unittest.mock import Mock

import pytest
import artin_sentinel.live as live


def test_audio_stop_during_spawn_reaps_late_player(monkeypatch):
    session = live.LiveAudioSession('rtsp://camera/main')
    child = Mock()
    child.poll.return_value = None
    child.wait.side_effect = lambda **kw: setattr(child.poll, 'return_value', 0)
    child.stderr = io.BytesIO()
    child.stdin = child.stdout = None
    monkeypatch.setattr(session, '_commands', lambda *a: [('fake', ['fake'])])
    def spawn(*a, **kw):
        session.stop()
        return child
    monkeypatch.setattr(live.subprocess, 'Popen', spawn)
    assert session._try_player(session.url, 'tcp') == (False, 'interrompido')
    assert child.poll() == 0 and child.stderr.closed
    assert session._process is None
    assert session.current_state == 'stopped'


def test_audio_stop_repeated_reaps_real_player_and_finishes_worker(monkeypatch):
    session = live.LiveAudioSession('rtsp://camera/main')
    spawned = threading.Event()
    children = []
    original = subprocess.Popen
    def spawn(*a, **kw):
        child = original(*a, **kw)
        children.append(child)
        spawned.set()
        return child
    monkeypatch.setattr(live.subprocess, 'Popen', spawn)
    monkeypatch.setattr(session, '_commands', lambda *a: [('fake', [sys.executable, '-c', 'import time; time.sleep(20)'])])
    monkeypatch.setattr(session, '_run', lambda: session._try_player(session.url, 'tcp'))
    session.start()
    assert spawned.wait(2)
    session.stop()
    session.stop()
    assert session.wait_closed(2)
    assert len(children) == 1 and children[0].poll() is not None
    assert session._process is None
    session.start()
    assert len(children) == 1


@pytest.mark.parametrize('probe,state', [
    (live.MediaProbeResult(video_codec='h264', video_present=True, audio_present=False), 'no_audio'),
    (live.MediaProbeResult(error_code='timeout'), 'error'),
    (live.MediaProbeResult(audio_codec='unsupported', audio_present=True), 'unsupported_codec'),
    (live.MediaProbeResult(error_code='authentication'), 'authentication'),
])
def test_audio_absence_is_not_confused_with_unavailable_stream_or_decoder(monkeypatch, probe, state):
    session = live.LiveAudioSession('rtsp://camera/main')
    monkeypatch.setattr(live.LiveAudioSession, 'player_available', property(lambda _: True))
    monkeypatch.setattr(live, 'probe_rtsp_media_capabilities', lambda *a, **kw: probe)
    monkeypatch.setattr(live, 'local_decoder_available', lambda _: False)
    session._run()
    assert session.current_state == state
    assert ('Sem faixa' in session.latest_status()) == (state == 'no_audio')


def test_close_during_audio_probe_never_starts_player(monkeypatch):
    session = live.LiveAudioSession('rtsp://camera/main')
    monkeypatch.setattr(live.LiveAudioSession, 'player_available', property(lambda _: True))
    def probe(*a, **kw):
        session.stop()
        return live.MediaProbeResult(audio_codec='aac', audio_present=True)
    monkeypatch.setattr(live, 'probe_rtsp_media_capabilities', probe)
    player = Mock()
    monkeypatch.setattr(session, '_try_player', player)
    session._run()
    player.assert_not_called()
    assert session.current_state == 'stopped'


def test_audio_reconnect_backoff_resets_only_after_sustained_playback(monkeypatch):
    session = live.LiveAudioSession('rtsp://camera/main')
    runs, waits = [], []
    def run():
        runs.append(1)
        session._had_audio = True
        session._last_player_duration = 6 if len(runs) == 5 else 0
        session._set_state('error')
    def wait(delay):
        waits.append(delay)
        if len(waits) == 6:
            session.stop()
        return session._stop.is_set()
    monkeypatch.setattr(session, '_run', run)
    monkeypatch.setattr(session._stop, 'wait', wait)
    session._run_wrapper()
    assert waits == [2, 5, 10, 30, 2, 2]
    assert session.finished


def test_stopped_volume_attachment_cannot_apply_gain(monkeypatch):
    stopped = threading.Event()
    stopped.set()
    inputs = Mock()
    monkeypatch.setattr(live, '_pulse_sink_inputs_for_pid', inputs)
    monkeypatch.setattr(live.shutil, 'which', lambda _: '/pactl')
    assert live.set_process_audio_gain(1, 75, retries=18, cancel_event=stopped)[0] is False
    inputs.assert_not_called()


@pytest.mark.parametrize('kind', [live.LiveAudioSession, live.LiveStreamSession])
def test_live_diagnostics_redact_known_plain_and_encoded_credentials(kind):
    session = kind('rtsp://camera/main', 'user name', 'secret phrase')
    message = 'user name secret phrase user%20name secret+phrase rtsp://user:pw@host'
    if isinstance(session, live.LiveAudioSession):
        session._push(session.diagnostics, message)
    else:
        session._push_diag(message)
    text = ' '.join(session.drain_diagnostics())
    assert 'secret' not in text and 'user' not in text and 'pw@' not in text


@pytest.mark.parametrize('state,label', [
    ('no_audio', 'SEM ÁUDIO'), ('unsupported_codec', 'ÁUDIO INDISPONÍVEL'),
    ('authentication', 'FALHA DE AUTENTICAÇÃO'), ('retrying', 'RECUPERANDO'),
])
def test_audio_current_state_exposes_specific_operational_label(state, label):
    session = live.LiveAudioSession('rtsp://camera/main')
    session._set_state(state)
    assert session.current_state_text() == label

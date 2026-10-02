from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QToolButton, QSlider, QLabel, QFrame

import artin_sentinel.talkback as talkback
import artin_sentinel.app as app


@pytest.mark.parametrize('protocol', sorted(talkback.IMPLEMENTED_TALKBACK_PROTOCOLS))
def test_implemented_route_still_requires_capability_channel_and_direct_endpoint(protocol):
    params = dict(scope_ok=True, evidence=True, route_kind='direct', netsdk_available=True)
    assert talkback.talkback_capability_status(protocol, **params) == 'ready'
    assert talkback.talkback_capability_status(protocol, **(params | {'scope_ok': False})) == 'wrong_channel'
    assert talkback.talkback_capability_status(protocol, **(params | {'evidence': False})) == 'no_capability'
    assert talkback.talkback_capability_status(protocol, **(params | {'route_kind': 'via_recorder'})) == 'recorder_route'


def test_no_speculative_transport_or_missing_netsdk_becomes_ready():
    params = dict(scope_ok=True, evidence=True, route_kind='direct')
    assert talkback.talkback_capability_status('onvif-backchannel', **params) == 'transport_unimplemented'
    assert talkback.talkback_capability_status('unvalidated', **params) == 'transport_unimplemented'
    assert talkback.talkback_capability_status('intelbras-netsdk-talk-experimental', **params) == 'runtime_missing'


@pytest.mark.parametrize('overrides,expected', [
    ({'microphone': None}, 'microphone_missing'),
    ({'scan_complete': False}, 'microphone_scanning'),
    ({'ffmpeg_available': False}, 'ffmpeg_missing'),
    ({'credentials': None}, 'credentials_missing'),
    ({}, 'ready'),
])
def test_preflight_reports_local_dependency_without_device_io(overrides, expected):
    params = dict(microphone=talkback.MicrophoneInput('pulse', 'default', 'MIC'), scan_complete=True,
                  credentials=('admin', 's3cret'), ffmpeg_available=True)
    info = dict(can_talk=True, talkback_protocol='xm-dvrip-g711a-experimental')
    result = talkback.talkback_start_readiness(info, **(params | overrides))
    assert result.code == expected
    assert result.ready == (expected == 'ready')
    assert 's3cret' not in result.detail


@pytest.mark.parametrize('session_type', [talkback.XmDvripTalkbackSession, talkback.IntelbrasHttpTalkbackSession,
                                          talkback.IntelbrasNetSDKTalkbackSession])
def test_every_transport_redacts_known_secrets_and_headers(session_type):
    session = session_type('192.0.2.1', 'admin', 's3cret space')
    session._push(session.diagnostics, 'admin s3cret space s3cret%20space https://admin:s3cret@host/ password=other\nAuthorization: Basic token\nsessão 0x123a')
    log = '\n'.join(session.drain_diagnostics())
    for secret in ('admin', 's3cret', 'other', 'Basic token', '0x123a'):
        assert secret not in log


def test_channel_capability_does_not_project_native_transport_to_recorder_route(monkeypatch):
    monkeypatch.setattr(app, 'intelbras_netsdk_runtime_info', lambda: SimpleNamespace(available=False, detail='missing'))
    device = dict(provider='it-blue', name='X3-WE2Q', manufacturer='IT-Blue', model='X3-WE2Q',
                  metadata_json='{"akdb_profile":"it-blue-x3-we2q"}')
    channel = dict(channel_no=1, source_name='Lente PTZ', route_kind='direct', audio_mode='unknown')
    direct = app.channel_audio_info(device, channel)
    recorder = app.channel_audio_info(device, channel | {'route_kind': 'via_recorder'})
    fixed = app.channel_audio_info(device, channel | {'channel_no': 2, 'source_name': 'Lente fixa'})
    assert direct['can_talk']
    assert not recorder['can_talk'] and recorder['talkback_state'] == 'recorder_route'
    assert not fixed['can_talk'] and not fixed['talkback_pending']


@pytest.fixture
def audio_window(monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = app.MainWindow.__new__(app.MainWindow)
    QMainWindow.__init__(window)
    window.selected_video_tile = SimpleNamespace(index=0)
    window.listen_audio_btn = QToolButton()
    window.talkback_btn = QToolButton()
    window.talkback_btn.setCheckable(True)
    window.audio_volume_slider = QSlider()
    window.audio_capability_label = QLabel()
    window.mic_progress_label = QLabel()
    window.audio_section = QFrame()
    window.live_audio_session = None
    window.live_audio_tile_index = None
    window.microphone_inputs = []
    window.microphone_scan_complete = True
    window.microphone_scan_future = None
    window.audio_input_preferences = talkback.AudioInputPreferences()
    window.mic_traces = {}
    window.talkback_session = None
    monkeypatch.setattr(window, '_selected_microphone_input', lambda: None)
    yield window
    window.hide(); window.deleteLater(); application.processEvents()


@pytest.mark.parametrize('has_context', [True, False])
def test_active_talkback_stop_remains_enabled_after_selection_or_capability_loss(audio_window, monkeypatch, has_context):
    window = audio_window
    info = dict(can_listen=False, can_talk=False)
    monkeypatch.setattr(window, '_audio_context_for_tile', lambda tile: ({}, {}, info, []) if has_context else None)
    window.talkback_session = SimpleNamespace(stop=Mock())
    window.talkback_tile_index = 9  # Active session belongs to a different tile.
    window.refresh_selected_audio_controls()
    assert window.talkback_btn.isEnabled()
    assert window.talkback_btn.text() == 'PARAR'
    window.toggle_selected_talkback()
    window.talkback_session.stop.assert_called_once()


def test_missing_capture_tool_is_explained_and_disables_start(audio_window, monkeypatch):
    window = audio_window
    info = dict(can_listen=False, can_talk=True, talkback_protocol='xm-dvrip-g711a-experimental')
    monkeypatch.setattr(window, '_audio_context_for_tile', lambda tile: ({}, {}, info, []))
    monkeypatch.setattr(app.shutil, 'which', lambda name: None)
    window.microphone_inputs = [talkback.MicrophoneInput('pulse', 'default', 'MIC')]
    window.refresh_selected_audio_controls()
    assert not window.talkback_btn.isEnabled()
    assert 'FFmpeg' in window.talkback_btn.toolTip()
    assert 'FFmpeg' in window.audio_capability_label.text()

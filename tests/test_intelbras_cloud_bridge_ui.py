import os
import time
from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMainWindow, QLineEdit, QDialogButtonBox, QLabel

from artin_sentinel.db import Database
from artin_sentinel.credential_store import CredentialStore


def test_bridge_dialog_connects_without_nested_event_loop_or_plaintext_persistence(tmp_path, monkeypatch):
    from artin_sentinel.intelbras_cloud_ui import open_bridge_dialog
    app = QApplication.instance() or QApplication([])
    source = Path(__file__).parent / 'fixtures/cloud_sdk_fake.cpp'
    sdk = tmp_path / 'sdk'
    sdk.mkdir()
    subprocess.run(['g++', '-std=c++17', '-shared', '-fPIC', '-pthread',
                    str(source), '-o', str(sdk / 'libdhnetsdk.so')], check=True)
    monkeypatch.setenv('FAKE_TRACE', str(tmp_path / 'trace'))
    host = QMainWindow()
    host.db = Database(tmp_path / 'inventory.sqlite3')
    host.current_site_id = host.db.add_site('Teste')
    host.credential_store = CredentialStore()
    host.session_credentials = {}
    host._transient_dialogs = []
    host.bottom_notice = QLabel()
    host._credentials_for_device = lambda did: None
    host.refresh_all = lambda: None
    host._stop_device_live_sessions = lambda did: None
    host.recorder_executor = ThreadPoolExecutor(max_workers=1)
    host._release_transient_dialog = lambda dialog: host._transient_dialogs.remove(dialog)
    dialog = open_bridge_dialog(host, sdk_dir=sdk, initial_mode="external")
    assert dialog.isVisible()
    dialog.findChild(QLineEdit, 'cloudSerial').setText('TEST-SERIAL-PRIVATE')
    dialog.findChild(QLineEdit, 'cloudUser').setText('TEST-USER-PRIVATE')
    dialog.findChild(QLineEdit, 'cloudPassword').setText('TEST-PASSWORD-PRIVATE')
    buttons = dialog.findChild(QDialogButtonBox)
    buttons.button(QDialogButtonBox.Ok).click()
    limit = time.monotonic() + 5
    while not host.db.list_devices() and time.monotonic() < limit:
        app.processEvents()
        time.sleep(0.01)
    host.recorder_executor.shutdown(wait=True)
    app.processEvents()
    devices = host.db.list_devices()
    assert len(devices) == 1
    did = devices[0]['id']
    assert len(host.db.list_recorder_channels(did)) == 4
    assert host.session_credentials[did] == ('TEST-USER-PRIVATE', 'TEST-PASSWORD-PRIVATE')
    assert not devices[0]['credential_saved']
    assert 'TEST-PASSWORD-PRIVATE' not in str(list(host.db.conn.iterdump()))
    assert not dialog.isVisible()
    host.close()


def test_cloud_video_reaches_real_sentinel_tile_and_marks_only_seen_channel(tmp_path, monkeypatch):
    from artin_sentinel import app as sentinel
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('ARTIN_AKDB_PATH', str(tmp_path / 'akdb.sqlite3'))
    sdk = tmp_path / 'data/artin-sentinel/vendor/intelbras-netsdk'
    sdk.mkdir(parents=True)
    monkeypatch.setenv('ARTIN_SENTINEL_NETSDK_DIR', str(sdk))
    subprocess.run(['g++', '-std=c++17', '-shared', '-fPIC', '-pthread',
                    str(Path(__file__).parent / 'fixtures/cloud_sdk_fake.cpp'),
                    '-o', str(sdk / 'libdhnetsdk.so')], check=True)
    payload = tmp_path / 'red.ts'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=160x90:r=10',
                    '-t', '2', '-c:v', 'mpeg2video', '-f', 'mpegts', str(payload)], check=True)
    monkeypatch.setenv('FAKE_TRACE', str(tmp_path / 'trace'))
    monkeypatch.setenv('FAKE_PAYLOAD', str(payload))
    monkeypatch.setattr(sentinel, 'password_dialog', lambda *a, **k: True)
    window = sentinel.MainWindow()
    try:
        did = register_bridge_inventory(window.db, window.current_site_id, 'Remoto',
                                        'TEST-SERIAL-PRIVATE', 55162, 4)
        window.session_credentials[did] = ('TEST-USER-PRIVATE', 'TEST-PASSWORD-PRIVATE')
        channels = window.db.list_recorder_channels(did)
        tile = window.video_tiles[0]
        window.apply_source_to_tile(tile, dict(type='channel', device_id=did, channel_id=channels[0]['id']))
        limit = time.monotonic() + 8
        while not window.db.get_recorder_channel(channels[0]['id'])['available'] and time.monotonic() < limit:
            app.processEvents()
            window.poll_live_streams()
            time.sleep(0.02)
        assert window.db.get_recorder_channel(channels[0]['id'])['available']
        assert not window.db.get_recorder_channel(channels[1]['id'])['available']
        assert window.live_sessions[tile.index].frame_count > 0
        assert 'Cloud' in window.live_sessions[tile.index].active_transport
    finally:
        window.close()
        app.processEvents()
    assert (tmp_path / 'trace').read_text().splitlines()[-3:] == ['stop', 'logout', 'cleanup']


def test_close_main_window_cancels_blocked_cloud_login(tmp_path, monkeypatch):
    from artin_sentinel import app as sentinel
    from artin_sentinel.intelbras_cloud_ui import open_bridge_dialog
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('ARTIN_AKDB_PATH', str(tmp_path / 'akdb.sqlite3'))
    sdk = tmp_path / 'sdk'
    sdk.mkdir()
    subprocess.run(['g++', '-std=c++17', '-shared', '-fPIC', '-pthread',
                    str(Path(__file__).parent / 'fixtures/cloud_sdk_fake.cpp'),
                    '-o', str(sdk / 'libdhnetsdk.so')], check=True)
    trace = tmp_path / 'trace'
    monkeypatch.setenv('ARTIN_SENTINEL_NETSDK_DIR', str(sdk))
    monkeypatch.setenv('FAKE_TRACE', str(trace))
    monkeypatch.setenv('FAKE_SCENARIO', 'hang_login')
    monkeypatch.setattr(sentinel, 'password_dialog', lambda *a, **k: True)
    window = sentinel.MainWindow()
    dialog = open_bridge_dialog(window, initial_mode="external")
    dialog.findChild(QLineEdit, 'cloudSerial').setText('TEST-SERIAL-PRIVATE')
    dialog.findChild(QLineEdit, 'cloudUser').setText('TEST-USER-PRIVATE')
    dialog.findChild(QLineEdit, 'cloudPassword').setText('TEST-PASSWORD-PRIVATE')
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    limit = time.monotonic() + 3
    while (not trace.exists() or 'login' not in trace.read_text()) and time.monotonic() < limit:
        app.processEvents()
        time.sleep(0.01)
    assert trace.exists() and 'login' in trace.read_text()
    start = time.monotonic()
    window.close()
    window.recorder_executor.shutdown(wait=True)
    app.processEvents()
    assert time.monotonic() - start < 3
    assert not dialog.isVisible()

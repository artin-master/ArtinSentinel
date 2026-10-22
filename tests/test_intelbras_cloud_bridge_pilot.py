from artin_sentinel.live import create_live_stream_session
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest


SERIAL = 'TEST-SERIAL-PRIVATE'
USER = 'TEST-USER-PRIVATE'
PASSWORD = 'TEST-PASSWORD-PRIVATE'


@pytest.fixture
def sdk(tmp_path, monkeypatch):
    compiler = shutil.which('g++')
    if not compiler:
        pytest.skip('g++ necessário para o SDK sintético')
    source = Path(__file__).parent / 'fixtures' / 'cloud_sdk_fake.cpp'
    subprocess.run([compiler, '-std=c++17', '-shared', '-fPIC', '-pthread',
                    str(source), '-o', str(tmp_path / 'libdhnetsdk.so')], check=True)
    monkeypatch.setenv('FAKE_TRACE', str(tmp_path / 'trace'))
    return tmp_path


def test_probe_authenticates_once_in_child_and_cleans_up(sdk):
    from artin_sentinel.intelbras_cloud import probe_bridge
    result = probe_bridge(55162, SERIAL, USER, PASSWORD, sdk_dir=sdk)
    assert result == {'channels': 4, 'serial_verified': True}
    trace = (sdk / 'trace').read_text().splitlines()
    assert trace == ['init', 'login', 'logout', 'cleanup']


def test_wrong_tunnel_identity_never_opens_video(sdk):
    from artin_sentinel.intelbras_cloud import probe_bridge
    with pytest.raises(ValueError, match='serial'):
        probe_bridge(55162, 'WRONG-SERIAL', USER, PASSWORD, sdk_dir=sdk)
    assert (sdk / 'trace').read_text().splitlines() == ['init', 'login', 'logout', 'cleanup']


def test_login_failure_is_not_retried_or_exposed(sdk, monkeypatch, capfd):
    from artin_sentinel.intelbras_cloud import probe_bridge
    monkeypatch.setenv('FAKE_SCENARIO', 'password')
    with pytest.raises(ValueError, match='Login'):
        probe_bridge(55162, SERIAL, USER, PASSWORD, sdk_dir=sdk)
    assert (sdk / 'trace').read_text().splitlines() == ['init', 'login', 'cleanup']
    output = capfd.readouterr()
    assert PASSWORD not in output.out + output.err


def test_crashed_vendor_is_contained(sdk, monkeypatch):
    from artin_sentinel.intelbras_cloud import probe_bridge
    monkeypatch.setenv('FAKE_SCENARIO', 'crash')
    with pytest.raises(ValueError, match='processo'):
        probe_bridge(55162, SERIAL, USER, PASSWORD, sdk_dir=sdk)


def test_hung_cleanup_has_bounded_supervision(sdk, monkeypatch):
    from artin_sentinel.intelbras_cloud import probe_bridge
    monkeypatch.setenv('FAKE_SCENARIO', 'hang_cleanup')
    start = time.monotonic()
    with pytest.raises(ValueError, match='prazo'):
        probe_bridge(55162, SERIAL, USER, PASSWORD, sdk_dir=sdk, timeout=0.3)
    assert time.monotonic() - start < 3


@pytest.mark.parametrize('url', [
    'intelbras-cloud://192.0.2.1:55162/1?serial=ABCD',
    'intelbras-cloud://admin:secret@127.0.0.1:55162/1?serial=ABCD',
    'intelbras-cloud://127.0.0.1:55162/0?serial=ABCD',
    'intelbras-cloud://127.0.0.1:55162/1',
    'intelbras-cloud://127.0.0.1:55162/1?serial=ABCD&mode=0',
])
def test_invalid_route_is_rejected_before_native_load(url):
    from artin_sentinel.intelbras_cloud import parse_bridge_route
    with pytest.raises(ValueError):
        parse_bridge_route(url)


def test_inventory_does_not_promote_unseen_video_or_merge_other_devices(tmp_path):
    from artin_sentinel.db import Database
    from artin_sentinel.domain import Device
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    db = Database(tmp_path / 'inventory.sqlite3')
    site = db.add_site('Teste')
    original = db.upsert_device(Device(site_id=site, ip='192.0.2.1', name='Local'))
    did = register_bridge_inventory(db, site, 'Remoto', SERIAL, 55162, 4)
    channels = db.list_recorder_channels(did)
    assert len(channels) == 4
    assert all(not ch['available'] for ch in channels)
    assert channels[0]['main_rtsp_url'].startswith('intelbras-cloud://127.0.0.1:55162/1?')
    assert db.get_device(original)['ip'] == '192.0.2.1'
    ch_id = channels[0]['id']
    db.update_channel_alias(ch_id, 'Entrada')
    assert register_bridge_inventory(db, site, 'Remoto', SERIAL, 55163, 4) == did
    refreshed = db.list_recorder_channels(did)
    assert refreshed[0]['id'] == ch_id and refreshed[0]['alias'] == 'Entrada'
    assert ':55163/' in refreshed[0]['main_rtsp_url']


def test_received_cloud_frame_promotes_only_its_channel(tmp_path):
    from artin_sentinel.db import Database
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    db = Database(tmp_path / 'inventory.sqlite3')
    site = db.add_site('Teste')
    did = register_bridge_inventory(db, site, 'Remoto', SERIAL, 55162, 4)
    channels = db.list_recorder_channels(did)
    assert db.confirm_native_channel_frame(channels[0]['id'], route=channels[0]['main_rtsp_url'])
    assert db.get_recorder_channel(channels[0]['id'])['available']
    assert not db.get_recorder_channel(channels[1]['id'])['available']


def test_old_route_frame_cannot_validate_reconfigured_channel(tmp_path):
    from artin_sentinel.db import Database
    from artin_sentinel.intelbras_cloud import register_bridge_inventory
    db = Database(tmp_path / 'inventory.sqlite3')
    site = db.add_site('Teste')
    did = register_bridge_inventory(db, site, 'Remoto', SERIAL, 55162, 4)
    old = db.list_recorder_channels(did)[0]
    register_bridge_inventory(db, site, 'Remoto', SERIAL, 55163, 4)
    assert not db.confirm_native_channel_frame(old['id'], route=old['main_rtsp_url'])
    assert not db.get_recorder_channel(old['id'])['available']
    current = db.get_recorder_channel(old['id'])
    assert db.confirm_native_channel_frame(current['id'], route=current['main_rtsp_url'])


def test_sdk_directory_matches_existing_installer_and_env_override(tmp_path, monkeypatch):
    from artin_sentinel.intelbras_cloud import default_sdk_dir
    from artin_sentinel.intelbras_netsdk import vendor_install_directory
    monkeypatch.setenv('ARTIN_SENTINEL_NETSDK_DIR', str(tmp_path / 'chosen-sdk'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'different-data'))
    assert default_sdk_dir() == vendor_install_directory()


def test_real_ffmpeg_decodes_vendor_callback_and_stop_reaps_child(sdk, tmp_path, monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg necessário')
    payload = tmp_path / 'red.ts'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=160x90:r=10',
                    '-t', '2', '-c:v', 'mpeg2video', '-f', 'mpegts', str(payload)], check=True)
    monkeypatch.setenv('FAKE_PAYLOAD', str(payload))
    session = IntelbrasCloudLiveSession(
        f'intelbras-cloud://127.0.0.1:55162/1?serial={SERIAL}', USER, PASSWORD,
        sdk_dir=sdk,
    )
    session.start()
    frame = None
    limit = time.monotonic() + 8
    while time.monotonic() < limit and frame is None:
        frame = session.latest_frame()
        time.sleep(0.02)
    session.stop()
    assert session.wait_closed(5)
    assert frame is not None, session.drain_diagnostics()
    offset = ((frame.height // 2) * frame.width + frame.width // 2) * 3
    red, green, blue = frame.pixels[offset:offset + 3]
    assert red > 150 and green < 80 and blue < 80
    trace = (sdk / 'trace').read_text().splitlines()
    assert trace == ['init', 'login', 'realplay', 'stop', 'logout', 'cleanup']


def test_cloud_bridge_route_uses_isolated_netsdk_transport():
    session = create_live_stream_session(
        'intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE',
        'TEST-USER-PRIVATE', 'TEST-PASSWORD-PRIVATE',
    )
    assert type(session).__name__ == 'IntelbrasCloudLiveSession'


def test_existing_rtsp_transport_is_preserved():
    session = create_live_stream_session('rtsp://192.0.2.1/live')
    assert type(session).__name__ == 'LiveStreamSession'


@pytest.mark.parametrize('metadata', ['[]', 'null', '12', 'bad-json'])
def test_non_cloud_metadata_never_breaks_existing_devices(metadata):
    from artin_sentinel.intelbras_cloud import is_cloud_device
    assert not is_cloud_device({'metadata_json': metadata})


def test_managed_wine_live_uses_dynamic_port_and_releases_after_video(sdk,tmp_path,monkeypatch):
    from artin_sentinel.intelbras_cloud import IntelbrasCloudLiveSession
    from artin_sentinel import intelbras_wine
    from test_intelbras_wine_manager import fake_process
    import sys
    script=fake_process(tmp_path)
    manager=intelbras_wine.WineTunnelManager(root=tmp_path/'runtime',prefix=tmp_path/'prefix',
        command_factory=lambda report,stop,port:[sys.executable,str(script),str(report),str(stop),'ready','35551'])
    monkeypatch.setattr(intelbras_wine,'wine_manager',lambda:manager)
    monkeypatch.setenv('FAKE_EXPECT_PORT','35551')
    payload=tmp_path/'managed.ts'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=160x90:r=10',
                    '-t','2','-c:v','mpeg2video','-f','mpegts',str(payload)],check=True)
    monkeypatch.setenv('FAKE_PAYLOAD',str(payload))
    session=IntelbrasCloudLiveSession(
        f'intelbras-wine://127.0.0.1:37777/1?serial={SERIAL}',USER,PASSWORD,sdk_dir=sdk)
    try:
        session.start();frame=None;limit=time.monotonic()+8
        while time.monotonic()<limit and frame is None:
            frame=session.latest_frame();time.sleep(.02)
        assert frame is not None,session.drain_diagnostics()
    finally:
        session.stop();assert session.wait_closed(5)
        manager.shutdown()
    assert not manager.entries
    report=json.loads((manager.root/'last_session.json').read_text())
    assert report['cleanup_returned'] and report['child_exit_code']==0
    assert (sdk/'trace').read_text().splitlines()==['init','login','realplay','stop','logout','cleanup']

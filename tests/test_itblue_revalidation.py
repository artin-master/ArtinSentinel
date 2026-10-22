import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QToolButton

from artin_sentinel import ip_camera
from artin_sentinel.app import MainWindow, VideoTile
from artin_sentinel.db import Database
from artin_sentinel.domain import Device
from artin_sentinel.recorder import RecorderChannel
from artin_sentinel.xm_dvrip import DvripMediaProbe
from artin_sentinel.direct_revalidation import DirectChannelRetirement, scan_diagnostic

IP = '192.0.2.47'


def lens(number):
    main = f'rtsp://{IP}:554/user={{username}}_password={{password}}_channel=0_stream=0.sdp?real_stream' if number == 1 else f'dvrip://{IP}:34567?channel={number-1}&subtype=0'
    sub = main.replace('stream=0','stream=1') if number == 1 else main.replace('subtype=0','subtype=1')
    name = 'Lente PTZ' if number == 1 else f'Lente fixa {number-1}'
    return RecorderChannel(number,name,main,True,200,'Rota direta • IT-Blue X3 • '+name,
                           source_name=name,main_rtsp_url=main,sub_rtsp_url=sub,
                           route_kind='direct',channel_kind='ip')


@pytest.fixture
def inventory(tmp_path):
    db = Database(tmp_path/'inventory.db')
    did = db.upsert_device(Device(site_id=db.list_sites()[0]['id'],name='X3',ip=IP,provider='it-blue',kind='camera'))
    db.replace_recorder_channels(did,[lens(n) for n in (1,2,3)])
    yield db,did
    db.close()


@pytest.fixture
def probes(monkeypatch):
    monkeypatch.setattr(ip_camera,'dvrip_multilens_hints',lambda *a,**k:{})
    monkeypatch.setattr(ip_camera,'read_onvif_device_information',lambda *a,**k:{})
    monkeypatch.setattr(ip_camera,'validate_rtsp_media',lambda url,*a,**k:('_channel=0_' in url,'ffprobe confirmou hevc 1280x720 via TCP'))
    monkeypatch.setattr(ip_camera,'probe_dvrip_media',lambda *a,**k:DvripMediaProbe(True,codec='hevc',fps=12,detail='DVRIP HEVC 12 fps'))
    monkeypatch.setattr(ip_camera,'_video_frame_signature',lambda *a,**k:0)
    monkeypatch.setattr(ip_camera,'_video_frame_fingerprint',lambda *a,**k:'')
    monkeypatch.setattr(ip_camera,'_route_frame_signature',lambda *a,**k:0)
    monkeypatch.setattr(ip_camera,'_direct_audio_fields',lambda *a,**k:{})
    monkeypatch.setattr(ip_camera.time,'sleep',lambda *a:None)


def scan(db,did):
    return ip_camera.scan_direct_camera_streams(IP,'admin','secret',provider='it-blue',previous_channels=db.list_recorder_channels(did))


def test_three_confirmed_lenses_revalidate_even_with_identical_coarse_signatures(inventory,probes):
    db,did = inventory
    result = scan(db,did)
    assert [ch.channel for ch in result.channels] == [1,2,3]
    assert all(item['decision']=='retained_known_identity' for item in result.diagnostics)
    assert all('secret' not in repr(item) for item in result.diagnostics)
    assert {item['profile'] for item in result.diagnostics} == {'Main','Sub'}
    assert result.diagnostics[0]['codec'] == 'hevc'
    assert result.diagnostics[0]['resolution'] == '1280x720'


def test_temporarily_missing_fixed_lenses_preserve_ids_routes_and_preferences(inventory,probes,monkeypatch):
    db,did = inventory
    old = db.list_recorder_channels(did)
    db.update_channel_alias(old[1]['id'],'Fixa do portão')
    db.update_channel_preferred_stream(old[1]['id'],'sub')
    monkeypatch.setattr(ip_camera,'probe_dvrip_media',lambda *a,**k:DvripMediaProbe(False,detail='timeout'))
    result = scan(db,did)
    assert [ch.channel for ch in result.channels] == [1]
    states = db.reconcile_direct_camera_channels(did,result.channels,diagnostics=result.diagnostics)
    after = db.list_recorder_channels(did)
    assert [row['id'] for row in after] == [row['id'] for row in old]
    assert all(row['available'] for row in after)
    assert after[1]['alias'] == 'Fixa do portão' and after[1]['preferred_stream'] == 'sub'
    assert after[1]['rtsp_url'] == old[1]['rtsp_url']
    assert states['2']['state'] == states['3']['state'] == 'temporarily_unavailable'
    assert any(item['error']=='timeout' and item['position']==2 for item in result.diagnostics)


def test_ffprobe_failure_then_recovery_does_not_delete_or_renumber(inventory,probes,monkeypatch):
    db,did = inventory
    old_ids = [row['id'] for row in db.list_recorder_channels(did)]
    with monkeypatch.context() as patch:
        patch.setattr(ip_camera,'validate_rtsp_media',lambda *a,**k:(False,'ffprobe timeout'))
        patch.setattr(ip_camera,'probe_dvrip_media',lambda *a,**k:DvripMediaProbe(False,detail='timeout'))
        result = scan(db,did)
        assert result.channels == []
        states = db.reconcile_direct_camera_channels(did,[],diagnostics=result.diagnostics)
        assert states['1']['state'] == 'temporarily_unavailable'
    recovered = scan(db,did)
    states = db.reconcile_direct_camera_channels(did,recovered.channels,diagnostics=recovered.diagnostics)
    assert all(value['state']=='validated' for value in states.values())
    assert [row['id'] for row in db.list_recorder_channels(did)] == old_ids


def test_restores_legacy_rows_disabled_by_completed_single_result(inventory):
    db,did = inventory
    db.replace_recorder_channels(did,[lens(1)])  # reproduces 0.2.94 removal
    assert [row['available'] for row in db.list_recorder_channels(did)] == [1,0,0]
    states = db.reconcile_direct_camera_channels(did,[lens(1)])
    assert [row['available'] for row in db.list_recorder_channels(did)] == [1,1,1]
    assert states['2']['state'] == 'pending_revalidation'


def test_new_distinct_views_with_equal_media_metadata_are_not_deduplicated(probes,monkeypatch):
    monkeypatch.setattr(ip_camera,'validate_rtsp_media',lambda url,*a,**k:('_stream=0' in url,'ffprobe confirmou hevc 1280x720 via TCP'))
    def signature(url,*a,**k):
        return 0 if '_channel=0_' in url else (1<<144)-1 if '_channel=1_' in url else (1<<72)-1
    monkeypatch.setattr(ip_camera,'_video_frame_signature',signature)
    monkeypatch.setattr(ip_camera,'_paired_visual_alias',lambda *a,**k:False)
    monkeypatch.setattr(ip_camera,'probe_dvrip_media',lambda *a,**k:DvripMediaProbe(False,detail='timeout'))
    channels = ip_camera._scan_itblue_x3_multilens_rtsp(IP,'admin','secret')
    assert [channel.channel for channel in channels] == [1,2,3]


def test_single_lens_does_not_gain_fixed_placeholders(probes,monkeypatch):
    monkeypatch.setattr(ip_camera,'probe_dvrip_media',lambda *a,**k:DvripMediaProbe(False,detail='not supported'))
    result = ip_camera.scan_direct_camera_streams(IP,'admin','secret',provider='it-blue')
    assert [channel.channel for channel in result.channels] == [1]


def test_retirement_requires_explicit_evidence_and_cannot_be_a_timeout(inventory):
    db,did = inventory
    for evidence in ('timeout',DirectChannelRetirement(2,1,'timeout'),DirectChannelRetirement(2,3)):
        with pytest.raises(ValueError,match='insufficient'):
            db.reconcile_direct_camera_channels(did,[lens(1)],retirement_evidence=[evidence])
    assert all(row['available'] for row in db.list_recorder_channels(did))
    states = db.reconcile_direct_camera_channels(did,[lens(1)],retirement_evidence=[DirectChannelRetirement(2,1)])
    assert states['2']['state'] == 'retired'
    assert db.list_recorder_channels(did)[1]['available'] == 0
    db.reconcile_direct_camera_channels(did,[lens(1)])
    assert db.list_recorder_channels(did)[1]['available'] == 0


def test_scan_diagnostic_sanitizes_known_credentials():
    item = scan_diagnostic(2,'rtsp://admin:secret@192.0.2.47/path','Main',False,'password=secret admin timeout','admin','secret',previous='previously_validated')
    assert 'secret' not in repr(item) and 'admin' not in repr(item)
    assert item['error'] == 'timeout'


def test_finish_scan_preserves_live_tiles_and_lists_all_known_lenses(inventory,monkeypatch,tmp_path):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    monkeypatch.setattr('artin_sentinel.app.data_dir',lambda:tmp_path)
    application = QApplication.instance() or QApplication([])
    db,did = inventory
    w = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(w)
    w.db = db
    w.video_tiles = [VideoTile(i) for i in range(3)]
    old = db.list_recorder_channels(did)
    for tile,row in zip(w.video_tiles,old):
        tile.set_source(row['source_name'],'','playing',{'type':'channel','device_id':did,'channel_id':row['id']})
    w.selected_video_tile = w.video_tiles[0]
    w.bottom_notice = QLabel()
    w.channels_button = QToolButton()
    w.detached_windows = {}
    w.channel_scan_context = {'device_id':did,'device':db.get_device(did),'wait':Mock(),'direct_camera':True}
    for name in ('stop_tile_stream','save_live_workspace','refresh_all','refresh_selected_ptz_controls','refresh_live_inspector_visibility','show_channel_rows','_resume_monitor_after_recorder','apply_source_to_tile'):
        setattr(w,name,Mock())
    try:
        w._finish_recorder_channel_scan(channels=ip_camera.DirectCameraScanResult(channels=[lens(1)]))
        w.stop_tile_stream.assert_not_called()
        w.apply_source_to_tile.assert_not_called()
        assert all(tile.source for tile in w.video_tiles)
        assert len(w.show_channel_rows.call_args.args[1]) == 3
        assert 'removido' not in w.bottom_notice.text()
    finally:
        for tile in w.video_tiles: tile.deleteLater()
        w.deleteLater()
        application.processEvents()

import json

import pytest

from artin_sentinel.camera_events import CameraEvent, CameraEventState, normalize_event, correlated_channels
from artin_sentinel.db import Database
from artin_sentinel.domain import Device


@pytest.mark.parametrize('name,action,kind', [('VideoMotion','Start','motion_start'), ('MotionDetect','Stop','motion_stop'), ('HumanDetection','Start','human_start'), ('HumanDetect','Stop','human_stop'), ('Detect','Start','alarm_unknown'), ('VideoMotion',None,'alarm_unknown')])
def test_normalization(name, action, kind):
    event = normalize_event({'Name':'AlarmInfo', 'AlarmInfo':{'Event':name,'Status':action,'Channel':0,'Password':'secret','SessionID':'secret'}})
    assert event.kind == kind and event.channel == 0
    assert 'secret' not in repr(event)


@pytest.mark.parametrize('payload', [None, [], {'AlarmInfo':[]}, {'AlarmInfo':{'Event':42}}, {'Name':'KeepAlive','Event':'VideoMotion'}])
def test_malformed_dropped(payload):
    assert normalize_event(payload) is None


def test_unknown_channel_and_ambiguous_route_stays_device_scoped():
    assert normalize_event({'Event':'VideoMotion','Status':'Start','Channel':'0'}).channel is None
    rows = [{'id':10,'rtsp_url':'dvrip://192.0.2.1?channel=0'}, {'id':11,'rtsp_url':'dvrip://192.0.2.1?channel=0'}]
    assert correlated_channels(rows) == {}
    assert correlated_channels([{'id':12,'rtsp_url':'rtsp://192.0.2.1/user=admin_password=x_channel=1_stream=0.sdp'}]) == {1:12}


def test_dedup_reconnect_stop_timeout_and_isolation():
    recorded = []
    clock = [0]
    state = CameraEventState(lambda d,e: recorded.append((d,e)), clock=lambda:clock[0], ttl=30)
    start = CameraEvent('motion_start', 0)
    assert state.ingest(1,start,{0:10})
    assert not state.ingest(1,start,{0:10})  # includes replay after reconnect
    assert state.labels(1,10) == 'Movimento'
    assert state.labels(1,11) == state.labels(2,10) == ''
    assert state.ingest(1,CameraEvent('human_start',1),{1:11})
    assert state.ingest(2,start,{0:20})
    assert state.ingest(1,CameraEvent('motion_stop',0),{0:10})
    assert not state.ingest(1,CameraEvent('motion_stop',0),{0:10})
    clock[0] = 31
    state.expire()
    assert not state.active
    assert len(recorded) == 6
    assert recorded[-1][1].reason == 'safety_timeout'


def test_without_channel_never_marks_channel_and_unknown_is_rate_limited():
    recorded = []
    state = CameraEventState(lambda d,e: recorded.append(e))
    state.ingest(1,CameraEvent('motion_start',99),{0:10})
    assert state.labels(1,None) == 'Movimento'
    assert state.labels(1,10) == ''
    assert state.ingest(1,CameraEvent('alarm_unknown'))
    assert not state.ingest(1,CameraEvent('alarm_unknown'))
    state.clear_device(1)
    assert not state.active


def test_database_scopes_history_and_preserves_restart(tmp_path):
    path = tmp_path/'events.db'
    db = Database(path)
    site = db.list_sites()[0]['id']
    device = db.upsert_device(Device(site_id=site,ip='192.0.2.1',name='IT-Blue'))
    db.conn.execute("INSERT INTO recorder_channels(device_id,channel_no,updated_at) VALUES(?,?,?)",(device,1,'now'))
    db.conn.commit()
    channel = db.list_recorder_channels(device)[0]['id']
    state = CameraEventState(db.add_camera_event)
    event = CameraEvent('motion_start',0)
    assert state.ingest(device,event,{0:channel})
    assert not state.ingest(device,event,{0:channel})
    row = db.list_events()[0]
    assert row['device_id'] == device and row['site_id'] == site
    assert json.loads(row['message'])['channel_id'] == channel
    assert row['severity'] == 'info'
    with pytest.raises(ValueError,match='channel'):
        db.add_camera_event(device,CameraEvent('motion_start',999))
    db.close()
    db = Database(path)
    assert len(db.list_events()) == 1
    db.close()

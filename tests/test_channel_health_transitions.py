import pytest

from artin_sentinel.channel_health import ChannelHealthSample, channel_health_label
from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.recorder import RecorderChannel


@pytest.fixture
def inventory(tmp_path):
    db = Database(tmp_path / 'health.sqlite3')
    site = db.list_sites()[0]['id']
    did = db.upsert_device(Device(site_id=site, name='DVR', ip='192.0.2.1', kind=DeviceKind.DVR))
    db.replace_recorder_channels(did, [RecorderChannel(1, 'CAM 1', 'rtsp://camera/1', True)])
    yield db, did
    db.close()


def test_same_problem_episode_does_not_repeat_on_state_flips(inventory):
    db, did = inventory
    for state in ['no_signal', 'no_signal', 'offline', 'no_signal', 'offline']:
        db.apply_channel_health_samples(did, [ChannelHealthSample(1, state, authoritative=True)], failure_threshold=1)
    assert len([e for e in db.list_events() if e['event_type'] == 'channel_problem']) == 1
    row = db.list_recorder_channels(did)[0]
    assert row['available'] == 1
    assert row['rtsp_url'] == 'rtsp://camera/1'
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'ok')])
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'ok')])
    assert len([e for e in db.list_events() if e['event_type'] == 'channel_recovered']) == 1


def test_transient_failure_never_creates_problem_or_recovery_history(inventory):
    db, did = inventory
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'offline')])
    assert db.list_recorder_channels(did)[0]['health_state'] == 'degraded'
    assert not db.list_recorder_channels(did)[0]['health_last_problem_at']
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'ok')])
    assert db.list_events() == []
    assert channel_health_label(db.list_recorder_channels(did)[0]) == 'OK'


def test_recovered_label_is_visible_for_first_positive_check(inventory):
    db, did = inventory
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'no_signal')], failure_threshold=1)
    problem = db.list_recorder_channels(did)[0]['health_last_problem_at']
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'ok')])
    row = db.list_recorder_channels(did)[0]
    assert row['health_last_problem_at'] == problem
    assert channel_health_label(row) == 'RECUPERADO'
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'ok')])
    assert channel_health_label(db.list_recorder_channels(did)[0]) == 'OK'


def test_unknown_observation_preserves_confirmed_loss_and_history(inventory):
    db, did = inventory
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'offline')], failure_threshold=1)
    previous = dict(db.list_recorder_channels(did)[0])
    db.apply_channel_health_samples(did, [ChannelHealthSample(1, 'unknown')])
    row = db.list_recorder_channels(did)[0]
    assert row['health_state'] == 'offline'
    assert row['health_last_problem_at'] == previous['health_last_problem_at']
    assert row['available'] == previous['available']
    assert len(db.list_events()) == 1


@pytest.mark.parametrize('state,label', [
    ('ok', 'OK'), ('offline', 'OFFLINE'), ('no_signal', 'SEM SINAL'),
    ('degraded', 'CONFIRMANDO'), ('unverified', 'INCONCLUSIVO'), ('unknown', 'SEM ESTADO'),
])
def test_distinct_health_labels(state, label):
    assert channel_health_label({'health_state': state}) == label
    assert channel_health_label({'health_state': state}, device_online=False) == 'EQUIP. OFFLINE'

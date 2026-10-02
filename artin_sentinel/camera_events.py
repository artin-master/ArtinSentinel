"""Conservative local event normalization/state. No raw payload persistence."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
import time
from urllib.parse import urlparse, parse_qs

EVENT_TYPES = frozenset({'motion_start', 'motion_stop', 'human_start', 'human_stop', 'alarm_unknown'})


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@dataclass(frozen=True)
class CameraEvent:
    kind: str
    channel: int | None = None
    received_at: str = ''
    source: str = 'dvrip-sofia'
    reason: str = 'notification'
    native_channel: int | None = None


def normalize_event(payload):
    if not isinstance(payload, dict):
        return None
    body = payload.get('AlarmInfo', payload if payload.get('Name') in (None, 'AlarmInfo') else None)
    if not isinstance(body, dict):
        return None
    name = body.get('Event')
    if not isinstance(name, str) or not name or len(name) > 80:
        return None
    channel = body.get('Channel')
    if type(channel) is not int or not 0 <= channel <= 255:
        channel = None
    action = body.get('Status', body.get('Action'))
    families = {'VideoMotion': 'motion', 'MotionDetect': 'motion', 'HumanDetection': 'human', 'HumanDetect': 'human', 'PersonDetect': 'human'}
    family = families.get(name)
    state = {'Start': 'start', 'Stop': 'stop'}.get(action) if isinstance(action, str) else None
    kind = f'{family}_{state}' if family and state else 'alarm_unknown'
    return CameraEvent(kind, channel, timestamp(), native_channel=channel)


def correlated_channels(rows):
    """Map native zero-based indices to DB channel IDs only from known XM routes.

    Inventory channel_no alone is insufficient evidence. Ambiguous routes are
    omitted; the notification remains equipment-scoped.
    """
    mapping = {}
    ambiguous = set()
    for row in rows:
        for field in ('rtsp_url', 'main_rtsp_url', 'sub_rtsp_url'):
            url = str(row[field] or '') if field in row.keys() else ''
            parsed = urlparse(url)
            native = None
            if parsed.scheme == 'dvrip':
                values = parse_qs(parsed.query).get('channel', [])
                if len(values) == 1 and values[0].isdigit():
                    native = int(values[0])
            elif parsed.scheme == 'rtsp':
                match = re.search(r'(?:^|_)channel=(\d+)_stream=', parsed.path)
                if match:
                    native = int(match.group(1))
            if native is None or not 0 <= native <= 255:
                continue
            channel_id = int(row['id'])
            if native in mapping and mapping[native] != channel_id:
                ambiguous.add(native)
            mapping[native] = channel_id
    return {index: channel for index, channel in mapping.items() if index not in ambiguous}


def verified_event_channels(device, rows):
    """Require recorded physical event/stream correlation for this firmware/IP.

    Route indices alone are candidates, not proof for multi-lens alarm engines.
    No automatic mapping or capability promotion is performed.
    """
    import json
    try:
        metadata = json.loads(device['metadata_json'] or '{}')
    except (ValueError, TypeError, KeyError, IndexError):
        return {}
    evidence = metadata.get('dvrip_event_channel_correlation') if isinstance(metadata, dict) else None
    if not isinstance(evidence, dict) or evidence.get('source') != 'physical_test':
        return {}
    if evidence.get('endpoint') != device['ip'] or not device['firmware'] or evidence.get('firmware') != device['firmware']:
        return {}
    candidates = correlated_channels(rows)
    pairs = evidence.get('channels')
    if not isinstance(pairs, list):
        return {}
    mapping = {}
    for pair in pairs[:256]:
        if not isinstance(pair, dict):
            continue
        native, channel_id = pair.get('native_channel'), pair.get('channel_id')
        if type(native) is int and type(channel_id) is int and candidates.get(native) == channel_id:
            mapping[native] = channel_id
    return mapping


class CameraEventState:
    def __init__(self, persist, *, clock=time.monotonic, ttl=30, unknown_window=5, replay_window=2):
        self.persist = persist
        self.clock = clock
        self.ttl = ttl
        self.unknown_window = unknown_window
        self.replay_window = replay_window
        self.started = {}
        self.active = {}
        self.unknown_seen = {}
        self.last = {}

    def ingest(self, device_id, event, channel_map=None):
        if not isinstance(event, CameraEvent) or event.kind not in EVENT_TYPES:
            return False
        event = replace(event, channel=(channel_map or {}).get(event.channel), native_channel=event.channel)
        now = self.clock()
        self.last[device_id] = event
        if event.kind == 'alarm_unknown':
            key = (device_id, event.channel, event.native_channel)
            if now - self.unknown_seen.get(key, float('-inf')) < self.unknown_window:
                return False
            self.persist(device_id, event)
            self.unknown_seen[key] = now
            return True
        family, action = event.kind.split('_')
        key = (device_id, event.channel, family, event.native_channel if event.channel is None else None)
        if action == 'start':
            if key in self.active:
                self.active[key] = (event, now + self.ttl)
                return False
            if now - self.started.get(key, float("-inf")) < self.replay_window:
                return False
            self.persist(device_id, event)
            self.started[key] = now
            self.active[key] = (event, now + self.ttl)
        elif key in self.active:
            self.persist(device_id, event)
            del self.active[key]
        else:
            return False  # orphan/duplicate Stop never creates history
        return True

    def expire(self):
        now = self.clock()
        for key, (event, deadline) in list(self.active.items()):
            if now >= deadline:
                device, channel, family, native = key
                expired = replace(event, kind=f'{family}_stop', received_at=timestamp(), reason='safety_timeout')
                self.persist(device, expired)
                del self.active[key]
        self.started = {key: when for key, when in self.started.items() if now - when < self.replay_window}
        self.unknown_seen = {key: when for key, when in self.unknown_seen.items() if now - when < self.unknown_window}

    def clear_device(self, device):
        for key, (event, deadline) in list(self.active.items()):
            if key[0] == device:
                self.persist(device, replace(event, kind=f'{key[2]}_stop', received_at=timestamp(), reason='subscription_stopped'))
                del self.active[key]

    def labels(self, device, channel):
        labels = []
        for did, cid, family, native in self.active:
            if did == device and cid == channel:
                labels.append('Pessoa' if family == 'human' else 'Movimento')
        return ' · '.join(sorted(set(labels)))

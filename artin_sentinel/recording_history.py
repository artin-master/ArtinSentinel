"""Bounded daily recording inventory. An unsuccessful query never proves absence."""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
import hashlib
import json
import os


@dataclass(frozen=True)
class DayCheck:
    day: date
    state: str
    earliest: datetime | None = None
    checked_at: datetime = field(default_factory=datetime.now)
    reason: str = ''


@dataclass(frozen=True)
class HistoryResult:
    days: tuple[DayCheck, ...]
    earliest: datetime | None
    verified: bool
    cancelled: bool
    range_start: date | None
    range_end: date | None


def scan_days(query, channel, dates, *, oldest=False, cancel_event=None, progress=None):
    dates = sorted(set(dates))
    if len(dates) > 3660 or not 1 <= int(channel) <= 256:
        raise ValueError('Consulta limitada a dez anos e um canal válido.')
    checks = []; earliest = None; errors = 0
    for day in dates:
        if cancel_event is not None and cancel_event.is_set():
            break
        begin = datetime.combine(day, time.min); end = begin + timedelta(days=1)
        fatal = False
        try:
            result = query(channel, begin, end)
            hits = []
            malformed = False
            for record in result.recordings:
                try:
                    start = datetime.fromisoformat(record.start)
                    finish = datetime.fromisoformat(record.end)
                    if record.channel == channel and finish > begin and start < end and finish > start:
                        hits.append(max(begin, start))
                except (ValueError, TypeError):
                    malformed = True
            partial = bool(result.truncated or result.warnings or result.ignored or malformed)
            candidate = min(hits) if hits else None
            state = 'partial' if partial else ('recorded' if candidate else 'empty')
            check = DayCheck(day, state, candidate)
            errors = 0
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                break
            check = DayCheck(day, 'error', reason=type(exc).__name__)
            errors += 1
            # Do not repeatedly submit rejected credentials or a mismatched identity.
            message = str(exc).lower()
            fatal = any(token in message for token in ('401', '403', 'login', 'senha', 'credencial', 'serial'))
        checks.append(check)
        if check.earliest is not None:
            earliest = min(earliest, check.earliest) if earliest else check.earliest
        if progress is not None:
            progress(len(checks), len(dates), check)
        if fatal or errors >= 3 or (oldest and check.earliest is not None):
            break
    cancelled = bool(cancel_event is not None and cancel_event.is_set())
    covered = len(checks) == len(dates) or bool(oldest and earliest)
    verified = covered and not cancelled and all(c.state in ('empty', 'recorded') for c in checks)
    return HistoryResult(tuple(checks), earliest, verified, cancelled,
                         dates[0] if dates else None, dates[-1] if dates else None)


class HistoryCache:
    """Only hashed device/channel scopes and date evidence; never credentials or routes."""
    def __init__(self, path):
        self.path = Path(path)
        try:
            raw = json.loads(self.path.read_text())
            self.entries = raw if isinstance(raw, dict) else {}
        except (ValueError, OSError):
            self.entries = {}

    @staticmethod
    def _key(scope, day):
        return hashlib.sha256(str(scope).encode()).hexdigest() + '/' + day.isoformat()

    def get(self, scope, day):
        try:
            value = self.entries[self._key(scope, day)]
            checked = datetime.fromisoformat(value['checked_at'])
            if not timedelta(0) <= datetime.now() - checked < timedelta(hours=12):
                return None
            if value['state'] not in ('recorded', 'empty', 'partial', 'error'):
                return None
            return DayCheck(day, value['state'], datetime.fromisoformat(value['earliest']) if value.get('earliest') else None, checked)
        except (KeyError, ValueError, TypeError):
            return None

    def put(self, scope, check):
        self.entries[self._key(scope, check.day)] = {
            'state': check.state, 'earliest': check.earliest.isoformat() if check.earliest else None,
            'checked_at': check.checked_at.isoformat()}
        if len(self.entries) > 5000:
            self.entries = dict(sorted(self.entries.items(), key=lambda pair: pair[1].get('checked_at', ''))[-5000:])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix('.pending')
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(self.entries, stream)
        os.replace(pending, self.path)


def run_history(device, route, username, password, channel, dates, *, oldest=False,
                cancel_event=None, progress=None):
    """Worker entry point with an immutable snapshot and one Wine lease per job."""
    from urllib.parse import urlparse
    lease = None
    try:
        from .hik_sdk import settings as hik_settings
        if hik_settings(device)["enabled"]:
            from .hik_sdk import search_recordings as sdk_search
            def query(ch,begin,end):
                return sdk_search(device,username,password,(ch,),begin,end,cancel_event=cancel_event)
            return scan_days(query,channel,dates,oldest=oldest,cancel_event=cancel_event,progress=progress)
        parsed = urlparse(route)
        if parsed.scheme in ('intelbras-cloud', 'intelbras-wine'):
            from .intelbras_cloud import parse_bridge_route
            from .intelbras_cloud_recordings import search_cloud_recordings
            port, serial, _ = parse_bridge_route(route)
            if parsed.scheme == 'intelbras-wine':
                from .intelbras_wine import wine_manager
                lease = wine_manager().acquire(serial, port, cancel_event=cancel_event)
                route = parsed._replace(scheme='intelbras-cloud', netloc=f'127.0.0.1:{lease.port}').geturl()
            def query(ch, begin, end):
                return search_cloud_recordings(route, username, password, (ch,), begin, end, cancel_event=cancel_event)
        else:
            identity = (str(device.get('manufacturer', '')) + ' ' + str(device.get('provider', ''))).lower()
            from .hik_recording import uses_hikvision_recordings
            if uses_hikvision_recordings(device):
                from .hik_recording import search_hikvision_recordings as search
            elif 'intelbras' in identity:
                from .recording_search import search_recordings as search
            else:
                raise ValueError('Histórico disponível para Intelbras e Hikvision compatíveis.')
            def query(ch, begin, end):
                return search(device['web_url'], username, password, ch, begin, end, **({'cancel_event':cancel_event} if cancel_event is not None and uses_hikvision_recordings(device) else {}))
        return scan_days(query, channel, dates, oldest=oldest, cancel_event=cancel_event, progress=progress)
    finally:
        if lease is not None:
            lease.release()

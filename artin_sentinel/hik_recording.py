"""Bounded read-only Hikvision ISAPI recording search and returned RTSP routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPBasicAuthHandler, HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from uuid import uuid4

from .recording_search import Recording, SearchResult, RecordingSearchError, _base_url, _NoRedirect


def _child(node, name):
    for element in node.iter():
        if element.tag.rsplit('}', 1)[-1] == name:
            return (element.text or '').strip()
    return ''


def _local_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone().replace(tzinfo=None)


def _utc_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def search_hikvision_recordings(web_url: str, username: str, password: str, channel: int,
                                 start: datetime, end: datetime, *, opener=None) -> SearchResult:
    if not 1 <= int(channel) <= 64 or end <= start or end - start > timedelta(hours=24):
        raise RecordingSearchError('Canal ou período inválido para busca Hikvision')
    base = _base_url(web_url)
    if opener is None:
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, base + '/', username, password)
        opener = build_opener(HTTPDigestAuthHandler(manager), HTTPBasicAuthHandler(manager), _NoRedirect())
    found = []
    warnings = []
    truncated = False
    track = int(channel) * 100 + 1
    for position in (0, 40, 80):
        body = (f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<CMSearchDescription version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
                f'<searchID>{uuid4()}</searchID><trackIDList><trackID>{track}</trackID></trackIDList>'
                f'<timeSpanList><timeSpan><startTime>{_utc_time(start)}</startTime>'
                f'<endTime>{_utc_time(end)}</endTime></timeSpan></timeSpanList>'
                f'<maxResults>40</maxResults><searchResultPostion>{position}</searchResultPostion>'
                f'</CMSearchDescription>').encode('utf-8')
        request = Request(base + '/ISAPI/ContentMgmt/search', data=body, method='POST',
                          headers={'Content-Type': 'application/xml', 'User-Agent': 'Artin-Sentinel/RecordingSearch'})
        try:
            with opener.open(request, timeout=8.0) as response:
                data = response.read(512 * 1024)
        except HTTPError as exc:
            raise RecordingSearchError(f'Busca ISAPI Hikvision falhou (HTTP {exc.code})') from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise RecordingSearchError('Gravador Hikvision indisponível para busca ISAPI') from exc
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise RecordingSearchError('Resposta de gravações Hikvision inválida') from exc
        if root.tag.rsplit('}', 1)[-1] != 'CMSearchResult':
            raise RecordingSearchError('Resposta ISAPI não contém resultados de gravação')
        matches = [node for node in root.iter() if node.tag.rsplit('}', 1)[-1] == 'searchMatchItem']
        for item in matches:
            try:
                if int(_child(item, 'trackID')) != track:
                    continue
                begin = _local_time(_child(item, 'startTime'))
                finish = _local_time(_child(item, 'endTime'))
                uri = _child(item, 'playbackURI')
                parsed = urlparse(uri)
                if not (begin < finish and begin < end and finish > start
                        and parsed.scheme == 'rtsp' and parsed.hostname and not parsed.username
                        and parsed.path.startswith('/Streaming/tracks/')):
                    continue
                found.append(Recording(channel, begin.strftime('%Y-%m-%d %H:%M:%S'),
                                       finish.strftime('%Y-%m-%d %H:%M:%S'),
                                       _child(item, 'metadataDescriptor')[:24] or 'gravação', 0,
                                       playback_uri=uri))
            except (ValueError, OverflowError):
                continue
        status = _child(root, 'responseStatusStrg').upper()
        if status != 'MORE' or len(matches) < 40:
            break
        truncated = position == 80
    return SearchResult(tuple(sorted(found, key=lambda row: row.start)), truncated, 0, tuple(warnings))


def hikvision_playback_url(recording: Recording, host: str, start: datetime, end: datetime,
                           *, port: int = 554) -> str:
    """Use the returned segment URI, rerouted to the enrolled recorder endpoint."""
    parsed = urlparse(recording.playback_uri)
    destination = urlparse(_base_url(host))
    if (parsed.scheme != 'rtsp' or not parsed.path.startswith('/Streaming/tracks/')
            or parsed.username or not 1 <= int(port) <= 65535 or end <= start):
        raise RecordingSearchError('URL de reprodução Hikvision inválida')
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    try:
        original_start = datetime.strptime(params['starttime'], '%Y%m%dT%H%M%SZ')
        clip_start = datetime.strptime(recording.start, '%Y-%m-%d %H:%M:%S')
    except (KeyError, ValueError) as exc:
        raise RecordingSearchError('Trecho Hikvision sem horário de reprodução') from exc
    params['starttime'] = (original_start + (start - clip_start)).strftime('%Y%m%dT%H%M%SZ')
    params['endtime'] = (original_start + (end - clip_start)).strftime('%Y%m%dT%H%M%SZ')
    return urlunparse(('rtsp', f'{destination.hostname}:{int(port)}', parsed.path, '', urlencode(params), ''))


def search_hikvision_recordings_multi(web_url, username, password, channels, start, end):
    if not channels or len(channels) > 4 or len(set(channels)) != len(channels):
        raise RecordingSearchError('Selecione de uma a quatro câmeras distintas')
    rows, warnings = [], []
    truncated = False
    for channel in channels:
        try:
            result = search_hikvision_recordings(web_url, username, password, channel, start, end)
            rows.extend(result.recordings)
            truncated |= result.truncated
        except RecordingSearchError as exc:
            warnings.append(f'CAM {channel}: {exc}')
    return SearchResult(tuple(sorted(rows, key=lambda row: (row.start, row.channel))), truncated, 0, tuple(warnings))

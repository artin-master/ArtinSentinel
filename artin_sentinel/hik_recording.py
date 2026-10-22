"""Bounded read-only Hikvision ISAPI recording search and returned RTSP routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPBasicAuthHandler, HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from uuid import uuid4
import hashlib
import time

from .recording_search import Recording, SearchResult, RecordingSearchError, _base_url, _NoRedirect


def uses_hikvision_recordings(device):
    """Route by explicit protocol/identity; never change the displayed brand."""
    from .device_intelligence import recorder_provider_hint
    return device is not None and recorder_provider_hint(device) in {"hikvision", "jfl"}


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
                                 start: datetime, end: datetime, *, opener=None, cancel_event=None) -> SearchResult:
    if not 1 <= int(channel) <= 64 or end <= start or end - start > timedelta(hours=24):
        raise RecordingSearchError('Canal ou período inválido para busca Hikvision')
    if cancel_event is not None and cancel_event.is_set():
        raise RecordingSearchError("Pesquisa de gravações cancelada")
    base = _base_url(web_url)
    if opener is None:
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, base + '/', username, password)
        opener = build_opener(HTTPDigestAuthHandler(manager), HTTPBasicAuthHandler(manager), _NoRedirect())
    found = []
    warnings = []
    truncated = False
    ignored = 0
    track = int(channel) * 100 + 1
    search_id = uuid4()
    position = 0
    seen = set()
    started=time.monotonic()
    seen_pages=set()
    for page_number in range(8):
        if cancel_event is not None and cancel_event.is_set():
            raise RecordingSearchError('Pesquisa de gravações cancelada')
        if time.monotonic()-started>40:
            truncated=True;warnings.append('Prazo da busca atingido; selecione um período menor.');break
        body = (f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<CMSearchDescription version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
                f'<searchID>{search_id}</searchID><trackIDList><trackID>{track}</trackID></trackIDList>'
                f'<timeSpanList><timeSpan><startTime>{_utc_time(start)}</startTime>'
                f'<endTime>{_utc_time(end)}</endTime></timeSpan></timeSpanList>'
                f'<maxResults>40</maxResults><searchResultPostion>{position}</searchResultPostion>'
                f'</CMSearchDescription>').encode('utf-8')
        request = Request(base + '/ISAPI/ContentMgmt/search', data=body, method='POST',
                          headers={'Content-Type': 'application/xml', 'User-Agent': 'Artin-Sentinel/RecordingSearch'})
        try:
            with opener.open(request, timeout=8.0) as response:
                data = response.read(512 * 1024 + 1)
                if len(data) > 512 * 1024:
                    raise RecordingSearchError("Resposta de gravações excedeu o limite de tamanho")
        except HTTPError as exc:
            hint={401:'Conta não autenticada para a pesquisa.',403:'Conta sem permissão de reprodução.',404:'Pesquisa ISAPI indisponível neste firmware.'}.get(exc.code,'Pesquisa não concluída.')
            raise RecordingSearchError(f'Busca ISAPI Hikvision falhou (HTTP {exc.code}). {hint}') from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise RecordingSearchError('Gravador Hikvision indisponível para busca ISAPI') from exc
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise RecordingSearchError('Resposta de gravações Hikvision inválida') from exc
        if root.tag.rsplit('}', 1)[-1] != 'CMSearchResult':
            raise RecordingSearchError('Resposta ISAPI não contém resultados de gravação')
        status = _child(root, 'responseStatusStrg').upper()
        if _child(root, 'responseStatus').lower() == 'false' or status not in {'', 'OK', 'MATCHES', 'MORE', 'NO MATCHES', 'NO MATCH', 'NOMATCHES'}:
            raise RecordingSearchError('Gravador não concluiu a busca ISAPI de gravações')
        digest=hashlib.sha256(data).digest()
        if digest in seen_pages:
            truncated=True;warnings.append('Gravador repetiu uma página da pesquisa; resultados parciais.');break
        seen_pages.add(digest)
        matches = [node for node in root.iter() if node.tag.rsplit('}', 1)[-1] == 'searchMatchItem']
        for item in matches:
            try:
                if int(_child(item, 'trackID')) != track:
                    ignored += 1
                    continue
                begin = _local_time(_child(item, 'startTime'))
                finish = _local_time(_child(item, 'endTime'))
                uri = _child(item, 'playbackURI')
                parsed = urlparse(uri)
                if begin >= end or finish <= start:
                    continue
                if not (begin < finish and parsed.scheme == 'rtsp' and parsed.hostname and not parsed.username
                        and parsed.path.startswith('/Streaming/tracks/')):
                    ignored += 1
                    continue
                key = (begin, finish, uri)
                if key in seen:
                    continue
                seen.add(key)
                found.append(Recording(channel, begin.strftime('%Y-%m-%d %H:%M:%S'),
                                       finish.strftime('%Y-%m-%d %H:%M:%S'),
                                       _child(item, 'metadataDescriptor')[:24] or 'gravação', 0,
                                       playback_uri=uri))
            except (ValueError, OverflowError):
                ignored += 1
                continue
        if status != 'MORE':
            break
        if not matches:
            truncated = True
            warnings.append('Gravador informou mais resultados sem retornar novos itens; reduza o período.')
            break
        position += len(matches)
        truncated = page_number == 7
    return SearchResult(tuple(sorted(found, key=lambda row: row.start)), truncated, ignored, tuple(warnings),
                        (f"Hikvision ISAPI • {len(seen_pages)} página(s) • {len(found)} trecho(s) • {ignored} descartado(s) • {time.monotonic()-started:.2f}s",))


def hikvision_playback_url(recording: Recording, host: str, start: datetime, end: datetime,
                           *, port: int = 554) -> str:
    """Use the returned segment URI, rerouted to the enrolled recorder endpoint."""
    parsed = urlparse(recording.playback_uri)
    destination = urlparse(_base_url(host))
    if (parsed.scheme != 'rtsp' or not parsed.path.startswith('/Streaming/tracks/')
            or parsed.username or not 1 <= int(port) <= 65535 or end <= start):
        raise RecordingSearchError('URL de reprodução Hikvision inválida')
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    clip_end = datetime.strptime(recording.end, '%Y-%m-%d %H:%M:%S')
    clip_begin = datetime.strptime(recording.start, '%Y-%m-%d %H:%M:%S')
    if start < clip_begin or end > clip_end:
        raise RecordingSearchError('Trecho fora do intervalo gravado selecionado')
    try:
        original_start = datetime.strptime(params['starttime'], '%Y%m%dT%H%M%SZ')
        clip_start = datetime.strptime(recording.start, '%Y-%m-%d %H:%M:%S')
    except (KeyError, ValueError) as exc:
        raise RecordingSearchError('Trecho Hikvision sem horário de reprodução') from exc
    params['starttime'] = (original_start + (start - clip_start)).strftime('%Y%m%dT%H%M%SZ')
    params['endtime'] = (original_start + (end - clip_start)).strftime('%Y%m%dT%H%M%SZ')
    destination_host = destination.hostname
    if ':' in destination_host:
        destination_host = '[' + destination_host + ']'
    return urlunparse(('rtsp', f'{destination_host}:{int(port)}', parsed.path, '', urlencode(params), ''))


def search_hikvision_recordings_multi(web_url, username, password, channels, start, end, *, cancel_event=None):
    if not channels or len(channels) > 4 or len(set(channels)) != len(channels):
        raise RecordingSearchError('Selecione de uma a quatro câmeras distintas')
    rows, warnings, diagnostics = [], [], []
    ignored = 0
    truncated = False
    for channel in channels:
        try:
            result = search_hikvision_recordings(web_url, username, password, channel, start, end,cancel_event=cancel_event)
            rows.extend(result.recordings)
            truncated |= result.truncated
            ignored += result.ignored
            warnings.extend(result.warnings);diagnostics.extend(result.diagnostics)
        except RecordingSearchError as exc:
            if cancel_event is not None and cancel_event.is_set():raise
            warnings.append(f'CAM {channel}: {exc}')
    return SearchResult(tuple(sorted(rows, key=lambda row: (row.start, row.channel))), truncated, ignored, tuple(warnings),tuple(diagnostics))

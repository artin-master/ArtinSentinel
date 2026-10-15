"""Bounded read-only Hikvision ISAPI recording search and returned RTSP routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import (
    Request, build_opener, HTTPBasicAuthHandler, HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
)
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from uuid import uuid4

from .recording_search import Recording, SearchResult, RecordingSearchError, _base_url, _NoRedirect


_PAGE_SIZE = 40
_MAX_PAGES = 3
_TRACK_RE = re.compile(r"^/Streaming/tracks/(\d+)/?$", re.IGNORECASE)


def _child(node, name):
    for element in node.iter():
        if element.tag.rsplit("}", 1)[-1] == name:
            return (element.text or "").strip()
    return ""


def _local_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def _utc_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_status(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9 _.-]", "", (value or "").strip())[:32]
    return clean or "desconhecido"


def _recording_size(uri: str) -> int:
    try:
        params = dict(parse_qsl(urlparse(uri).query, keep_blank_values=True))
        return max(0, int(params.get("size", "0")))
    except (TypeError, ValueError):
        return 0


def _validated_playback_uri(uri: str, track: int) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname or parsed.username or parsed.password:
        return False
    match = _TRACK_RE.fullmatch(parsed.path)
    return bool(match and int(match.group(1)) == int(track))


def _build_search_body(search_id: str, track: int, start: datetime, end: datetime, position: int) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CMSearchDescription version="1.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
        f"<searchID>{search_id}</searchID>"
        f"<trackIDList><trackID>{track}</trackID></trackIDList>"
        "<timeSpanList><timeSpan>"
        f"<startTime>{_utc_time(start)}</startTime>"
        f"<endTime>{_utc_time(end)}</endTime>"
        "</timeSpan></timeSpanList>"
        "<contentTypeList><contentType>video</contentType></contentTypeList>"
        "<metadataList><metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor></metadataList>"
        f"<maxResults>{_PAGE_SIZE}</maxResults>"
        f"<searchResultPostion>{position}</searchResultPostion>"
        "</CMSearchDescription>"
    ).encode("utf-8")


def _open_search(opener, base: str, body: bytes) -> bytes:
    request = Request(
        base + "/ISAPI/ContentMgmt/search",
        data=body,
        method="POST",
        headers={"Content-Type": "application/xml", "User-Agent": "Artin-Sentinel/RecordingSearch"},
    )
    try:
        with opener.open(request, timeout=8.0) as response:
            return response.read(512 * 1024)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RecordingSearchError(
                "A conta Hikvision não autorizou a consulta de gravações (HTTP 401/403)"
            ) from exc
        if exc.code == 404:
            raise RecordingSearchError(
                "Busca de gravações ISAPI indisponível neste firmware Hikvision (HTTP 404)"
            ) from exc
        raise RecordingSearchError(f"Busca ISAPI Hikvision falhou (HTTP {exc.code})") from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise RecordingSearchError("Gravador Hikvision indisponível para busca ISAPI") from exc


def search_hikvision_recordings(
    web_url: str,
    username: str,
    password: str,
    channel: int,
    start: datetime,
    end: datetime,
    *,
    opener=None,
) -> SearchResult:
    """Search up to 120 Hikvision recording segments for one logical channel.

    Hikvision documents searchID as the identity of a search session and the
    result position as its pagination cursor. Reusing the ID across pages is
    important for compatibility with older DVR/NVR firmware.
    """
    if not 1 <= int(channel) <= 64 or end <= start or end - start > timedelta(hours=24):
        raise RecordingSearchError("Canal ou período inválido para busca Hikvision")

    base = _base_url(web_url)
    if opener is None:
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, base + "/", username, password)
        opener = build_opener(
            HTTPDigestAuthHandler(manager), HTTPBasicAuthHandler(manager), _NoRedirect()
        )

    track = int(channel) * 100 + 1
    search_id = str(uuid4())
    found: list[Recording] = []
    seen: set[tuple[int, str, str, str]] = set()
    warnings: list[str] = []
    ignored = 0
    truncated = False

    for page in range(_MAX_PAGES):
        position = page * _PAGE_SIZE
        data = _open_search(
            opener, base, _build_search_body(search_id, track, start, end, position)
        )
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise RecordingSearchError("Resposta de gravações Hikvision inválida") from exc
        root_name = root.tag.rsplit("}", 1)[-1]
        if root_name == "ResponseStatus":
            detail = _safe_status(_child(root, "subStatusCode") or _child(root, "statusString"))
            raise RecordingSearchError(f"Gravador Hikvision rejeitou a consulta ISAPI ({detail})")
        if root_name != "CMSearchResult":
            raise RecordingSearchError("Resposta ISAPI não contém resultados de gravação")

        status = _child(root, "responseStatusStrg").upper()
        if status not in ("", "OK", "MORE"):
            raise RecordingSearchError(
                f"Gravador Hikvision recusou a busca ({_safe_status(status)})"
            )

        matches = [
            node for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "searchMatchItem"
        ]
        try:
            declared = int(_child(root, "numOfMatches") or len(matches))
        except ValueError:
            declared = len(matches)

        added_this_page = 0
        for item in matches:
            try:
                item_track = int(_child(item, "trackID"))
                begin = _local_time(_child(item, "startTime"))
                finish = _local_time(_child(item, "endTime"))
                uri = _child(item, "playbackURI")
            except (ValueError, OverflowError):
                ignored += 1
                continue

            if (
                item_track != track
                or not (begin < finish and begin < end and finish > start)
                or not _validated_playback_uri(uri, track)
            ):
                ignored += 1
                continue

            row = Recording(
                int(channel),
                begin.strftime("%Y-%m-%d %H:%M:%S"),
                finish.strftime("%Y-%m-%d %H:%M:%S"),
                _child(item, "metadataDescriptor")[:24] or "gravação",
                _recording_size(uri),
                playback_uri=uri,
            )
            key = (row.channel, row.start, row.end, row.playback_uri)
            if key in seen:
                continue
            seen.add(key)
            found.append(row)
            added_this_page += 1

        if status != "MORE":
            break
        if page == _MAX_PAGES - 1:
            truncated = True
            break
        if not matches or declared <= 0:
            warnings.append("DVR informou mais resultados, mas a página veio vazia")
            break
        if added_this_page == 0 and page > 0:
            warnings.append("DVR repetiu uma página de resultados; paginação interrompida com segurança")
            break

    return SearchResult(
        tuple(sorted(found, key=lambda row: row.start)),
        truncated,
        ignored,
        tuple(warnings),
    )


def hikvision_playback_url(
    recording: Recording,
    host: str,
    start: datetime,
    end: datetime,
    *,
    port: int = 554,
) -> str:
    """Use the returned segment URI, rerouted to the enrolled recorder endpoint."""
    parsed = urlparse(recording.playback_uri)
    destination = urlparse(_base_url(host))
    match = _TRACK_RE.fullmatch(parsed.path)
    if (
        parsed.scheme.lower() != "rtsp"
        or not match
        or parsed.username
        or parsed.password
        or not 1 <= int(port) <= 65535
        or end <= start
    ):
        raise RecordingSearchError("URL de reprodução Hikvision inválida")

    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    try:
        original_start = datetime.strptime(params["starttime"], "%Y%m%dT%H%M%SZ")
        clip_start = datetime.strptime(recording.start, "%Y-%m-%d %H:%M:%S")
        clip_end = datetime.strptime(recording.end, "%Y-%m-%d %H:%M:%S")
    except (KeyError, ValueError) as exc:
        raise RecordingSearchError("Trecho Hikvision sem horário de reprodução") from exc

    if start < clip_start or end > clip_end:
        raise RecordingSearchError("Intervalo solicitado está fora do trecho Hikvision")

    params["starttime"] = (original_start + (start - clip_start)).strftime("%Y%m%dT%H%M%SZ")
    params["endtime"] = (original_start + (end - clip_start)).strftime("%Y%m%dT%H%M%SZ")

    hostname = destination.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    return urlunparse(
        ("rtsp", f"{hostname}:{int(port)}", parsed.path, "", urlencode(params), "")
    )


def search_hikvision_recordings_multi(web_url, username, password, channels, start, end):
    if not channels or len(channels) > 4 or len(set(channels)) != len(channels):
        raise RecordingSearchError("Selecione de uma a quatro câmeras distintas")
    rows, warnings = [], []
    ignored = 0
    truncated = False
    for channel in channels:
        try:
            result = search_hikvision_recordings(
                web_url, username, password, channel, start, end
            )
            rows.extend(result.recordings)
            truncated |= result.truncated
            ignored += result.ignored
            warnings.extend(f"CAM {channel}: {warning}" for warning in result.warnings)
        except RecordingSearchError as exc:
            warnings.append(f"CAM {channel}: {exc}")
    return SearchResult(
        tuple(sorted(rows, key=lambda row: (row.start, row.channel))),
        truncated,
        ignored,
        tuple(warnings),
    )

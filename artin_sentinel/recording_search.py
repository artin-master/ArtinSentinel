"""Read-only Intelbras media file search using the documented HTTP finder."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import (
    HTTPBasicAuthHandler, HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm,
    HTTPRedirectHandler, Request, build_opener,
)


class RecordingSearchError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RecordingSearchError("Redirecionamento da busca bloqueado para proteger a credencial")


@dataclass(frozen=True)
class Recording:
    channel: int
    start: str
    end: str
    kind: str
    size: int
    playback_uri: str = ""


@dataclass(frozen=True)
class SearchResult:
    recordings: tuple[Recording, ...]
    truncated: bool = False
    ignored: int = 0
    warnings: tuple[str, ...] = ()


def playback_rtsp_url(host: str, channel_no: int, start: datetime, end: datetime, port: int = 554) -> str:
    """Intelbras HTTP API 4.1.2 playback stream; timestamps use recorder local time."""
    if not 1 <= channel_no <= 256 or not 1 <= port <= 65535 or end <= start:
        raise RecordingSearchError("Trecho de reprodução inválido")
    parsed = urlparse(_base_url(host))
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    return (f"rtsp://{hostname}:{port}/cam/playback?channel={channel_no}"
            f"&starttime={start:%Y_%m_%d_%H_%M_%S}&endtime={end:%Y_%m_%d_%H_%M_%S}")


def _base_url(web_url: str) -> str:
    parsed = urlparse(web_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise RecordingSearchError("Endereço Web do gravador inválido")
    return f"{parsed.scheme}://{parsed.netloc}"


def _pairs(data: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in data.splitlines() if "=" in line)


def _get(opener, base: str, **params) -> str:
    url = base + "/cgi-bin/mediaFileFind.cgi?" + urlencode(params, quote_via=quote)
    try:
        with opener.open(Request(url, headers={"User-Agent": "Artin-Sentinel/RecordingSearch"}), timeout=5.0) as response:
            return response.read(131073).decode("utf-8", "replace")[:131072]
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RecordingSearchError("Conta sem acesso à busca de gravações (HTTP 401/403)") from exc
        if exc.code == 404:
            raise RecordingSearchError("Busca de gravações CGI indisponível neste firmware (HTTP 404)") from exc
        raise RecordingSearchError(f"Consulta de gravações falhou (HTTP {exc.code})") from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise RecordingSearchError("Gravador indisponível para consulta de gravações") from exc


def search_recordings(
    web_url: str, username: str, password: str, channel_no: int,
    start: datetime, end: datetime, *, opener=None,
) -> SearchResult:
    if not 1 <= channel_no <= 256:
        raise RecordingSearchError("Selecione um canal válido")
    if end <= start or end - start > timedelta(hours=24):
        raise RecordingSearchError("O período deve ter até 24 horas e terminar após o início")
    base = _base_url(web_url)
    if opener is None:
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, base + "/", username, password)
        handlers = [HTTPDigestAuthHandler(manager), _NoRedirect()]
        if base.startswith("https://"):
            handlers.append(HTTPBasicAuthHandler(manager))
        opener = build_opener(*handlers)
    created = _pairs(_get(opener, base, action="factory.create"))
    object_id = created.get("result", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", object_id):
        raise RecordingSearchError("Gravador não forneceu identificador de busca válido")
    found: list[Recording] = []
    truncated = False
    ignored = 0
    try:
        answer = _get(
            opener, base, action="findFile", object=object_id,
            **{"condition.Channel": channel_no,
               "condition.StartTime": start.strftime("%Y-%m-%d %H:%M:%S"),
               "condition.EndTime": end.strftime("%Y-%m-%d %H:%M:%S")},
        ).strip()
        if answer != "OK":
            raise RecordingSearchError("Gravador não iniciou a busca de arquivos")
        for page in range(3):
            pairs = _pairs(_get(opener, base, action="findNextFile", object=object_id, count=100))
            try:
                count = int(pairs.get("found", "-1"))
            except ValueError as exc:
                raise RecordingSearchError("Resposta de gravações inválida") from exc
            if count < 0 or count > 100:
                raise RecordingSearchError("Resposta de gravações inválida")
            for i in range(count):
                prefix = f"items[{i}]."
                try:
                    recording = Recording(
                        channel=int(pairs.get(prefix + "Channel", str(channel_no))),
                        start=pairs[prefix + "StartTime"], end=pairs[prefix + "EndTime"],
                        kind=pairs.get(prefix + "Type", "—")[:24],
                        size=max(0, int(pairs.get(prefix + "Length", "0"))),
                    )
                    clip_start = datetime.strptime(recording.start, "%Y-%m-%d %H:%M:%S")
                    clip_end = datetime.strptime(recording.end, "%Y-%m-%d %H:%M:%S")
                    # The finder accepts 1-based condition.Channel and returns
                    # 0-based items[i].Channel (confirmed on the field MHDX).
                    # Never accept an adjacent channel as the selected camera.
                    if recording.channel == channel_no - 1 and clip_start < end and clip_end > start:
                        found.append(Recording(channel_no, recording.start, recording.end,
                                               recording.kind, recording.size))
                    else:
                        ignored += 1
                except (KeyError, ValueError) as exc:
                    raise RecordingSearchError("Arquivo de gravação com campos inválidos") from exc
            if count < 100:
                break
            truncated = page == 2
    finally:
        for action in ("close", "destroy"):
            try:
                _get(opener, base, action=action, object=object_id)
            except RecordingSearchError:
                pass
    return SearchResult(tuple(found), truncated, ignored)


def search_recordings_multi(web_url: str, username: str, password: str,
                            channels: tuple[int, ...], start: datetime, end: datetime) -> SearchResult:
    """Run independent bounded searches for up to four channels on one recorder."""
    if not channels or len(channels) > 4 or len(set(channels)) != len(channels):
        raise RecordingSearchError("Selecione de uma a quatro câmeras distintas")
    recordings = []
    warnings = []
    ignored = 0
    truncated = False
    for channel in channels:
        try:
            result = search_recordings(web_url, username, password, channel, start, end)
        except RecordingSearchError as exc:
            warnings.append(f"CAM {channel}: {exc}")
            continue
        recordings.extend(result.recordings)
        ignored += result.ignored
        truncated |= result.truncated
    return SearchResult(tuple(sorted(recordings, key=lambda r: (r.start, r.channel))),
                        truncated, ignored, tuple(warnings))

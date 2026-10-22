from __future__ import annotations

"""Official Intelbras/Dahua-compatible HTTP API capability probe.

The 0.2.36 foundation deliberately limits automatic probing to documented,
read-only endpoints.  No configuration is changed and no audio is posted by
this module.  A later transport can use ``postAudio`` only after the device
itself has positively advertised an audio output.
"""

from dataclasses import asdict, dataclass
from . import __version__
import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    HTTPSHandler,
    Request,
    build_opener,
)


API_VERSION_PATH = "/cgi-bin/IntervideoManager.cgi?action=getVersion&Name=CGI"
AUDIO_INPUT_PATH = "/cgi-bin/devAudioInput.cgi?action=getCollect"
AUDIO_OUTPUT_PATH = "/cgi-bin/devAudioOutput.cgi?action=getCollect"
POST_AUDIO_PATH = "/cgi-bin/audio.cgi?action=postAudio&httptype={httptype}&channel={channel}"
AUDIO_DECODE_EMPTY_PATH = "/cgi-bin/api/devAudioDecode/empty"


@dataclass(slots=True)
class IntelbrasHttpApiReport:
    supported: bool = False
    reachable: bool = False
    authenticated: bool = False
    base_url: str = ""
    api_version: str = ""
    audio_inputs: int | None = None
    audio_outputs: int | None = None
    post_audio_candidate: bool = False
    auth_scheme: str = ""
    detail: str = ""

    def as_metadata(self) -> dict:
        data = asdict(self)
        # This structure is safe to persist: it never includes credentials,
        # authorization headers, nonce/cnonce values or response bodies.
        return data

    def safe_summary(self) -> str:
        if not self.reachable:
            return self.detail or "API HTTP não respondeu"
        if not self.authenticated:
            return self.detail or "API respondeu, mas a autenticação não foi aceita"
        parts = ["Intelbras HTTP API detectada"]
        if self.api_version:
            parts.append(f"versão {self.api_version}")
        if self.audio_inputs is not None:
            parts.append(f"áudio IN {self.audio_inputs}")
        if self.audio_outputs is not None:
            parts.append(f"áudio OUT {self.audio_outputs}")
        parts.append("postAudio candidato" if self.post_audio_candidate else "postAudio não confirmado")
        return " • ".join(parts)




def post_audio_transport_info(metadata: dict | None) -> dict:
    """Resolve persisted read-only probe evidence into transport-safe fields.

    This does not probe or transmit anything. It only accepts a concrete device
    report that was authenticated and that declared at least one audio output.
    """
    report = metadata.get("intelbras_http_api") if isinstance(metadata, dict) else None
    ready = bool(
        isinstance(report, dict)
        and report.get("supported")
        and report.get("authenticated")
        and report.get("post_audio_candidate")
        and int(report.get("audio_outputs") or 0) > 0
    )
    return {
        "ready": ready,
        "base_url": str(report.get("base_url") or "") if ready else "",
        "audio_channel": 1 if ready else 0,
        "audio_outputs": int(report.get("audio_outputs") or 0) if isinstance(report, dict) else 0,
    }

def _kv_value(text: str, key: str) -> str:
    key_cf = str(key).casefold()
    for raw in str(text or "").splitlines():
        if "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        if name.strip().casefold() == key_cf:
            return value.strip()
    return ""


def _int_value(text: str, key: str = "result") -> int | None:
    raw = _kv_value(text, key)
    if not raw:
        return None
    match = re.search(r"-?\d+", raw)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _candidate_bases(host: str, *, web_url: str = "", open_ports=()) -> list[str]:
    """Return conservative local API bases, preferring the known web endpoint."""
    host = str(host or "").strip()
    ports = {int(p) for p in (open_ports or ()) if str(p).isdigit()}
    candidates: list[str] = []

    def add(url: str) -> None:
        url = str(url or "").strip().rstrip("/")
        if url and url not in candidates:
            candidates.append(url)

    if web_url:
        parsed = urlparse(str(web_url).strip())
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            port = f":{parsed.port}" if parsed.port else ""
            add(f"{parsed.scheme}://{parsed.hostname}{port}")
    if host:
        if 80 in ports or not ports:
            add(f"http://{host}")
        if 443 in ports:
            add(f"https://{host}")
        # Some inventories know a web URL but not its open_ports list. Keep a
        # final HTTP fallback because Intelbras recorder CGI commonly uses it.
        add(f"http://{host}")
    return candidates


def _build_digest_opener(base_url: str, username: str, password: str):
    manager = HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, base_url + "/", str(username), str(password))
    handlers = [HTTPDigestAuthHandler(manager)]
    if base_url.lower().startswith("https://"):
        handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
    return build_opener(*handlers)


def _get_text(opener, url: str, timeout: float) -> tuple[int, str, str]:
    request = Request(url, method="GET", headers={"User-Agent": f"Artin-Sentinel/{__version__}"})
    try:
        with opener.open(request, timeout=max(0.5, float(timeout))) as response:
            data = response.read(65536)
            return int(getattr(response, "status", 200) or 200), data.decode("utf-8", "replace"), ""
    except HTTPError as exc:
        scheme = str(exc.headers.get("WWW-Authenticate", "") or "")
        body = b""
        try:
            body = exc.read(4096)
        except Exception:
            pass
        return int(exc.code), body.decode("utf-8", "replace"), scheme
    except (URLError, OSError, TimeoutError) as exc:
        raise ConnectionError(str(exc)) from exc


def query_talkback_buffer_empty(
    base_url: str,
    username: str,
    password: str,
    *,
    audio_channel: int = 1,
    timeout: float = 1.5,
) -> tuple[bool | None, str]:
    """Query the V3.61+ documented talkback audio decoder buffer state.

    The V3.81 Intelbras HTTP specification documents
    ``POST /cgi-bin/api/devAudioDecode/empty`` with ``sourceType=0`` for
    talkback data. Request channels are zero-based for this JSON API, hence an
    operator-facing audio output channel 1 is queried as channel 0.

    Returns ``(flag, detail)`` where ``flag`` is ``True`` when the decoder
    buffer is empty, ``False`` when it contains talkback data, and ``None``
    when the firmware does not expose this diagnostic or the result cannot be
    established safely.
    """
    base = str(base_url or "").rstrip("/")
    if not base:
        return None, "base HTTP ausente"
    opener = _build_digest_opener(base, username, password)
    payload = json.dumps({
        "channel": max(0, int(audio_channel or 1) - 1),
        "sourceType": 0,
    }).encode("utf-8")
    request = Request(
        base + AUDIO_DECODE_EMPTY_PATH,
        data=payload,
        method="POST",
        headers={
            "User-Agent": f"Artin-Sentinel/{__version__}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with opener.open(request, timeout=max(0.5, float(timeout))) as response:
            status = int(getattr(response, "status", 200) or 200)
            raw = response.read(8192).decode("utf-8", "replace")
    except HTTPError as exc:
        code = int(exc.code)
        if code in {404, 501}:
            return None, f"devAudioDecode.empty não suportado (HTTP {code})"
        if code in {401, 403}:
            return None, f"devAudioDecode.empty sem autorização (HTTP {code})"
        return None, f"devAudioDecode.empty falhou (HTTP {code})"
    except (URLError, OSError, TimeoutError) as exc:
        return None, f"devAudioDecode.empty indisponível ({type(exc).__name__})"
    if status != 200:
        return None, f"devAudioDecode.empty retornou HTTP {status}"
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None, "devAudioDecode.empty respondeu JSON inválido"
    flag = data.get("flag")
    if isinstance(flag, bool):
        return flag, "buffer vazio" if flag else "buffer contém dados de talkback"
    return None, "devAudioDecode.empty não retornou flag booleana"


def probe_intelbras_http_api(
    host: str,
    username: str,
    password: str,
    *,
    web_url: str = "",
    open_ports=(),
    timeout: float = 2.5,
) -> IntelbrasHttpApiReport:
    """Probe documented read-only Intelbras HTTP API endpoints.

    A positive result means the concrete firmware answered the official CGI
    family with the supplied credential. ``post_audio_candidate`` is set only
    when that same firmware reports one or more audio output channels; it does
    *not* transmit audio and is not itself a talkback success claim.
    """
    last_detail = "Nenhum endpoint HTTP/HTTPS candidato respondeu."
    for base in _candidate_bases(host, web_url=web_url, open_ports=open_ports):
        opener = _build_digest_opener(base, username, password)
        report = IntelbrasHttpApiReport(base_url=base)
        try:
            v_status, v_text, v_auth = _get_text(opener, base + API_VERSION_PATH, timeout)
        except ConnectionError as exc:
            last_detail = f"{base}: {exc}"
            continue
        report.reachable = True
        if v_auth:
            report.auth_scheme = v_auth.split(None, 1)[0]
        if v_status in {401, 403}:
            report.detail = f"{base}: autenticação HTTP recusada ({v_status})"
            last_detail = report.detail
            # The endpoint exists; don't silently try another scheme and make a
            # bad credential look like a compatibility failure.
            return report

        version = _kv_value(v_text, "version") if v_status == 200 else ""
        # Version CGI may be absent on a particular firmware. Audio count CGIs
        # are independent read-only evidence of the same documented API family.
        try:
            in_status, in_text, _ = _get_text(opener, base + AUDIO_INPUT_PATH, timeout)
            out_status, out_text, _ = _get_text(opener, base + AUDIO_OUTPUT_PATH, timeout)
        except ConnectionError as exc:
            report.detail = f"{base}: conexão caiu durante a leitura de capacidades ({exc})"
            last_detail = report.detail
            continue

        auth_ok = any(code == 200 for code in (v_status, in_status, out_status))
        if not auth_ok:
            if any(code in {401, 403} for code in (in_status, out_status)):
                report.detail = f"{base}: API respondeu, mas a credencial não autorizou as consultas"
                last_detail = report.detail
                return report
            report.detail = f"{base}: CGIs oficiais não disponíveis neste firmware"
            last_detail = report.detail
            continue

        report.authenticated = True
        report.supported = True
        report.api_version = version
        report.audio_inputs = _int_value(in_text) if in_status == 200 else None
        report.audio_outputs = _int_value(out_text) if out_status == 200 else None
        report.post_audio_candidate = bool((report.audio_outputs or 0) > 0)
        report.detail = report.safe_summary()
        return report

    return IntelbrasHttpApiReport(detail=last_detail)

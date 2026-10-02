from __future__ import annotations

"""Experimental local Push-to-Talk transports and microphone discovery.

0.2.30 keeps the XM/IT-Blue return-audio path explicitly experimental, but
moves microphone discovery off the Qt event loop, remembers the selected local
source/gain, and follows the DVRIP/Sofia talk-channel handshake more closely.
"""

from dataclasses import asdict, dataclass
from functools import lru_cache
import base64
import ctypes
import hashlib
import http.client
import json
import os
import select
import socket
import ssl
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse, quote, quote_plus
from urllib.request import parse_http_list, parse_keqv_list

from . import __version__
from .log_viewer import sanitize_log_text
from .intelbras_http import API_VERSION_PATH, POST_AUDIO_PATH, query_talkback_buffer_empty
from .intelbras_netsdk import (
    IntelbrasNetSDK, NetSDKUnavailable, TalkFormat, DH_TALK_PCM, DH_TALK_G711A,
    EM_DEV_PROTOCOL_V3, runtime_info as netsdk_runtime_info, reference_audio_path,
)
from .xm_dvrip import DvripSession, DvripError


@dataclass(frozen=True, slots=True)
class TalkbackTransport:
    protocol: str
    label: str
    requires_netsdk: bool = False
    experimental: bool = True


# These are implemented local routes, not manufacturer-wide compatibility.
TALKBACK_TRANSPORTS = (
    TalkbackTransport("xm-dvrip-g711a-experimental", "DVRIP/Sofia G.711 A-law"),
    TalkbackTransport("intelbras-http-postaudio-experimental", "Intelbras HTTP postAudio/G.711 A-law"),
    TalkbackTransport("intelbras-netsdk-talk-experimental", "Intelbras NetSDK", requires_netsdk=True),
)
IMPLEMENTED_TALKBACK_PROTOCOLS = frozenset(item.protocol for item in TALKBACK_TRANSPORTS)


def talkback_transport(protocol: str) -> TalkbackTransport | None:
    return next((item for item in TALKBACK_TRANSPORTS if item.protocol == protocol), None)


TALKBACK_REASONS = {
    "no_capability": "Retorno de áudio não confirmado para este equipamento.",
    "wrong_channel": "Retorno de áudio não disponível nesta lente/canal.",
    "recorder_route": "A saída de áudio do equipamento não confirma retorno para uma câmera atrás do gravador.",
    "transport_unimplemented": "O transporte local de retorno ainda não está implementado/homologado.",
    "runtime_missing": "O runtime oficial Intelbras NetSDK não está disponível; importe em Configuração → Atualizações.",
    "ready": "Transporte experimental disponível; saída física de áudio ainda exige validação em campo.",
}


def talkback_capability_status(protocol: str, *, scope_ok: bool, evidence: bool,
                               route_kind: str, netsdk_available: bool = False) -> str:
    if not scope_ok:
        return "wrong_channel"
    if not evidence:
        return "no_capability"
    transport = talkback_transport(protocol)
    if transport is None:
        return "transport_unimplemented"
    if route_kind != "direct":
        return "recorder_route"
    if transport.requires_netsdk and not netsdk_available:
        return "runtime_missing"
    return "ready"


@dataclass(frozen=True, slots=True)
class TalkbackReadiness:
    code: str
    detail: str

    @property
    def ready(self) -> bool:
        return self.code == "ready"


def talkback_start_readiness(info: dict, *, microphone, scan_complete: bool,
                             credentials, ffmpeg_available: bool) -> TalkbackReadiness:
    """GUI-safe preflight; no device IO or multimedia enumeration here."""
    if not info.get("can_talk"):
        state = str(info.get("talkback_state") or "no_capability")
        return TalkbackReadiness(state, TALKBACK_REASONS.get(state, TALKBACK_REASONS["no_capability"]))
    if talkback_transport(str(info.get("talkback_protocol") or "")) is None:
        return TalkbackReadiness("transport_unimplemented", TALKBACK_REASONS["transport_unimplemented"])
    if not ffmpeg_available:
        return TalkbackReadiness("ffmpeg_missing", "FFmpeg não disponível para capturar o microfone local.")
    if not scan_complete:
        return TalkbackReadiness("microphone_scanning", "A detecção do microfone está em andamento. Tente novamente em instantes.")
    if microphone is None:
        return TalkbackReadiness("microphone_missing", "Nenhuma entrada Pulse/PipeWire ou ALSA compatível foi encontrada.")
    if not credentials:
        return TalkbackReadiness("credentials_missing", "Configure a credencial do equipamento antes de usar o microfone.")
    return TalkbackReadiness("ready", TALKBACK_REASONS["ready"])


def sanitize_talkback_diagnostic(text: object, username: str = "", password: str = "") -> str:
    """Redact known secrets even when an exception echoes them without a URL."""
    value = sanitize_log_text(text)
    value = re.sub(r"(?i)((?:https?|rtsps?)://)[^/@\s]+@", r"\1<oculto>@", value)
    for secret in (username, password):
        if not secret:
            continue
        for candidate in sorted({secret, quote(secret, safe=""), quote_plus(secret, safe="")}, key=len, reverse=True):
            if len(candidate) >= 3:
                value = value.replace(candidate, "<oculto>")
            else:
                value = re.sub(r"(?<![\w])" + re.escape(candidate) + r"(?![\w])", "<oculto>", value)
    value = re.sub(r"(?i)(\bsess[aã]o\s+)(?:0x[0-9a-f]+|[0-9a-f]{8,})\b", r"\1<oculto>", value)
    return value.strip()


@dataclass(frozen=True, slots=True)
class MicrophoneInput:
    backend: str
    source: str
    label: str

    @property
    def key(self) -> str:
        return f"{self.backend}:{self.source}"


@dataclass(slots=True)
class AudioInputPreferences:
    backend: str = "pulse"
    source: str = "default"
    gain_db: int = 0
    netsdk_talk_mode: str = "literal-reference"


def _audio_preferences_path(data_directory: Path) -> Path:
    return Path(data_directory) / "audio-input-settings.json"


def load_audio_input_preferences(data_directory: Path) -> AudioInputPreferences:
    defaults = AudioInputPreferences()
    path = _audio_preferences_path(data_directory)
    if not path.exists():
        return defaults
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    backend = str(payload.get("backend") or defaults.backend).strip().lower()
    if backend not in {"pulse", "alsa"}:
        backend = defaults.backend
    source = str(payload.get("source") or defaults.source).strip() or "default"
    try:
        gain_db = int(payload.get("gain_db", defaults.gain_db))
    except (TypeError, ValueError):
        gain_db = defaults.gain_db
    gain_db = max(-6, min(gain_db, 9))
    netsdk_talk_mode = str(payload.get("netsdk_talk_mode") or defaults.netsdk_talk_mode).strip().lower()
    if netsdk_talk_mode not in {"literal-reference", "literal-reference-wait", "literal-reference-speaker1", "live-pcm-literal", "live-g711a-server"}:
        netsdk_talk_mode = defaults.netsdk_talk_mode
    return AudioInputPreferences(
        backend=backend, source=source, gain_db=gain_db, netsdk_talk_mode=netsdk_talk_mode
    )


def save_audio_input_preferences(data_directory: Path, preferences: AudioInputPreferences) -> None:
    path = _audio_preferences_path(data_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(preferences), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@lru_cache(maxsize=1)
def ffmpeg_microphone_inputs() -> frozenset[str]:
    """Return microphone input backends present in the local FFmpeg build.

    This probe may take a few seconds on some systems and therefore must not be
    called directly from the Qt event loop. 0.2.30 only invokes it from worker
    threads/session threads.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return frozenset()
    try:
        cp = subprocess.run(
            [ffmpeg, "-hide_banner", "-devices"],
            capture_output=True,
            text=True,
            timeout=4.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")
    found = set()
    for name in ("pulse", "alsa"):
        if any(name in line.lower() and line.lstrip().startswith("D") for line in text.splitlines()):
            found.add(name)
    low = text.lower()
    if " pulse " in low or "pulse audio" in low:
        found.add("pulse")
    if " alsa " in low:
        found.add("alsa")
    return frozenset(found)


def _pulse_sources(timeout: float = 2.5) -> list[MicrophoneInput]:
    pactl = shutil.which("pactl")
    if not pactl:
        return []
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    default_source = ""
    try:
        cp = subprocess.run(
            [pactl, "get-default-source"], capture_output=True, text=True,
            timeout=min(timeout, 1.5), check=False, env=env,
        )
        default_source = (cp.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        cp = subprocess.run(
            [pactl, "list", "sources"], capture_output=True, text=True,
            timeout=timeout, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    result: list[MicrophoneInput] = []
    current: dict[str, str] = {}

    def flush() -> None:
        name = current.get("name", "").strip()
        description = current.get("description", "").strip()
        monitor = current.get("monitor", "").strip().lower()
        if not name or name.endswith(".monitor"):
            current.clear()
            return
        if monitor and monitor not in {"n/a", "none", "null"}:
            current.clear()
            return
        label = description or name
        if name == default_source:
            label += " (padrão)"
        result.append(MicrophoneInput("pulse", name, label))
        current.clear()

    for raw in (cp.stdout or "").splitlines():
        line = raw.strip()
        if line.startswith("Source #"):
            if current:
                flush()
            continue
        if line.startswith("Name:"):
            current["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("Description:"):
            current["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("Monitor of Sink:"):
            current["monitor"] = line.split(":", 1)[1].strip()
    if current:
        flush()

    # Default first, then stable label ordering. De-duplicate by persistent name.
    unique: dict[str, MicrophoneInput] = {item.source: item for item in result}
    result = list(unique.values())
    result.sort(key=lambda item: (0 if item.source == default_source else 1, item.label.casefold()))
    return result


def discover_microphone_inputs() -> list[MicrophoneInput]:
    """Discover concrete local microphone sources.

    Designed to run in a worker thread. Pulse/PipeWire sources are preferred
    because they have stable symbolic names (unlike transient PipeWire node IDs).
    """
    backends = ffmpeg_microphone_inputs()
    result: list[MicrophoneInput] = []
    if "pulse" in backends:
        result.extend(_pulse_sources())
        if not result:
            result.append(MicrophoneInput("pulse", "default", "Microfone padrão (Pulse/PipeWire)"))
    if "alsa" in backends:
        result.append(MicrophoneInput("alsa", "default", "Microfone padrão (ALSA)"))
    unique: dict[str, MicrophoneInput] = {}
    for item in result:
        unique.setdefault(item.key, item)
    return list(unique.values())




@dataclass(frozen=True, slots=True)
class MicrophoneLevelResult:
    ok: bool
    mean_db: float | None = None
    peak_db: float | None = None
    detail: str = ""


def probe_microphone_level(
    microphone: MicrophoneInput, *, gain_db: int = 0, duration: float = 1.25
) -> MicrophoneLevelResult:
    """Measure one local microphone in a bounded background-friendly FFmpeg probe.

    The helper never plays or stores audio. FFmpeg's volumedetect filter reports
    aggregate levels on stderr, which lets the UI calibrate quiet webcams without
    blocking the Qt event loop or opening a camera talkback connection.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return MicrophoneLevelResult(False, detail="FFmpeg não encontrado")
    backend = str(microphone.backend or "").lower()
    if backend not in {"pulse", "alsa"}:
        return MicrophoneLevelResult(False, detail=f"backend {backend or '?'} não suportado")
    gain_db = max(-6, min(int(gain_db), 9))
    duration = max(0.6, min(float(duration), 3.0))
    filters = []
    if gain_db:
        filters.append(f"volume={gain_db}dB")
    filters.append("volumedetect")
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "info",
        "-thread_queue_size", "256", "-f", backend, "-i", str(microphone.source or "default"),
        "-t", f"{duration:.2f}", "-af", ",".join(filters), "-f", "null", "-",
    ]
    try:
        cp = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=duration + 3.0, check=False)
    except subprocess.TimeoutExpired:
        return MicrophoneLevelResult(False, detail="tempo limite ao medir microfone")
    except OSError as exc:
        return MicrophoneLevelResult(False, detail=f"falha ao abrir microfone: {exc}")
    text = cp.stderr or ""
    mean_match = re.findall(r"mean_volume:\s*(-?inf|[-+]?\d+(?:\.\d+)?)\s*dB", text, flags=re.I)
    peak_match = re.findall(r"max_volume:\s*(-?inf|[-+]?\d+(?:\.\d+)?)\s*dB", text, flags=re.I)
    def parse(values):
        if not values:
            return None
        raw = values[-1].lower()
        if "inf" in raw:
            return -120.0
        try:
            return float(raw)
        except ValueError:
            return None
    mean_db = parse(mean_match)
    peak_db = parse(peak_match)
    if mean_db is None and peak_db is None:
        tail = " ".join(line.strip() for line in text.splitlines()[-3:] if line.strip())[-300:]
        return MicrophoneLevelResult(False, detail=tail or "FFmpeg não retornou nível de áudio")
    return MicrophoneLevelResult(True, mean_db=mean_db, peak_db=peak_db, detail="nível local medido")


def _terminate_process_nonblocking(proc: subprocess.Popen | None, grace: float = 0.7) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        return

    def reap() -> None:
        try:
            proc.wait(timeout=max(0.1, float(grace)))
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass

    threading.Thread(target=reap, name="sentinel-talkback-reaper", daemon=True).start()


class XmDvripTalkbackSession:
    """Capture a local microphone and send G.711 A-law through DVRIP OPTalk.

    The transport remains experimental. 0.2.35 follows the observed XM/iCSee
    topology: one authenticated control connection plus a secondary talk socket
    attached to the same SessionID and session-wide command sequence.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        microphone_backend: str = "pulse",
        microphone_source: str = "default",
        microphone_label: str = "",
        gain_db: int = 0,
        max_seconds: float = 18.0,
    ):
        self.host = str(host)
        self.username = str(username)
        self.password = str(password)
        self.microphone_backend = str(microphone_backend or "pulse").lower()
        self.microphone_source = str(microphone_source or "default")
        self.microphone_label = str(microphone_label or self.microphone_source)
        self.gain_db = max(-6, min(int(gain_db), 9))
        self.max_seconds = max(3.0, min(float(max_seconds), 30.0))
        self.status: queue.Queue[str] = queue.Queue(maxsize=8)
        self.diagnostics: queue.Queue[str] = queue.Queue(maxsize=24)
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._control_session: DvripSession | None = None
        self._talk_session: DvripSession | None = None

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    @property
    def available(self) -> bool:
        return bool(shutil.which("ffmpeg") and self.microphone_backend in {"pulse", "alsa"})

    def _push(self, q: queue.Queue[str], text: str) -> None:
        text = sanitize_talkback_diagnostic(text, self.username, self.password)
        if not text:
            return
        while True:
            try:
                q.put_nowait(text)
                return
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    return

    def latest_status(self) -> str | None:
        latest = None
        while True:
            try:
                latest = self.status.get_nowait()
            except queue.Empty:
                return latest

    def drain_diagnostics(self) -> list[str]:
        out = []
        while True:
            try:
                out.append(self.diagnostics.get_nowait())
            except queue.Empty:
                return out

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._finished.clear()
        self._thread = threading.Thread(target=self._run_wrapper, name="sentinel-talkback-xm", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request stop without blocking the Qt/event-loop caller.

        Keep the authenticated DVRIP socket alive until the worker can send a
        clean OPTalk Stop. Terminating FFmpeg wakes the microphone read quickly;
        the GUI thread never waits or joins.
        """
        self._stop.set()
        _terminate_process_nonblocking(self._process)
        # Start/Stop cleanup remains in the background worker. Never join here.

    def _capture_commands(self) -> list[tuple[str, list[str]]]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return []
        backends = ffmpeg_microphone_inputs()  # background thread only
        gain_filter = ["-af", f"volume={self.gain_db}dB"] if self.gain_db else []
        common_out = [
            *gain_filter,
            "-ac", "1", "-ar", "8000", "-c:a", "pcm_alaw", "-f", "alaw", "pipe:1",
        ]
        commands: list[tuple[str, list[str]]] = []

        def add(backend: str, source: str, label: str) -> None:
            if backend not in backends:
                return
            cmd = [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-thread_queue_size", "512", "-f", backend, "-i", source, *common_out,
            ]
            commands.append((label, cmd))

        add(self.microphone_backend, self.microphone_source, self.microphone_label or self.microphone_backend)
        if self.microphone_backend == "pulse" and self.microphone_source != "default":
            add("pulse", "default", "Pulse/PipeWire padrão (fallback)")
        if self.microphone_backend != "alsa":
            add("alsa", "default", "ALSA padrão (fallback)")
        return commands

    def _run_wrapper(self) -> None:
        try:
            self._run()
        except Exception as exc:
            if not self._stop.is_set():
                self._push(self.status, f"Push-to-Talk falhou: {type(exc).__name__}")
            self._push(self.diagnostics, f"{type(exc).__name__}: {exc}")
        finally:
            self._finished.set()

    def _run(self) -> None:
        commands = self._capture_commands()
        if not commands:
            self._push(self.status, "Microfone local indisponível no FFmpeg")
            return

        # 0.2.35 reference-compatible XM/iCSee path:
        # - one authenticated control connection owns the login session;
        # - a second TCP socket is attached to that SAME SessionID without a
        #   second login;
        # - the command sequence is continued across both sockets;
        # - Claim and 1432 audio use the talk socket, while Start/Stop remain
        #   on the authenticated control socket.
        # This matches the session topology observed by working DVRIP clients
        # and avoids the independent-session/Ret=504 failure mode.
        with DvripSession(self.host, self.username, self.password, timeout=3.0) as control:
            self._control_session = control
            sid = f"0x{int(control.session):08x}"
            self._push(self.diagnostics, f"DVRIP 1/6 • controle autenticado • sessão {sid}")

            talk = DvripSession(self.host, self.username, self.password, timeout=3.0)
            try:
                talk.attach_authenticated_session(control.session, control.sequence)
                self._talk_session = talk
                self._push(
                    self.diagnostics,
                    f"DVRIP 2/6 • socket de talk anexado à mesma sessão • seq {int(talk.sequence)}",
                )
                talk.talk_claim()
                # Claim consumed the next logical command sequence on the talk
                # socket. Continue from that exact value on the control socket.
                control.sync_sequence_from(talk)
                self._push(self.diagnostics, "DVRIP 3/6 • OPTalk Claim aceito no socket de talk")
                control.talk_start_no_reply()
                talk.sync_sequence_from(control)
                self._push(self.diagnostics, "DVRIP 4/6 • OPTalk Start enviado no canal de controle")
                self._push(self.status, "Falando • DVRIP/G.711A")
                self._push(
                    self.diagnostics,
                    f"Microfone: {self.microphone_label or self.microphone_source} • ganho {self.gain_db:+d} dB",
                )
                started = time.monotonic()
                sent_any = False
                frames_sent = 0
                bytes_sent = 0
                chosen_backend = ""
                try:
                    for backend, cmd in commands:
                        if self._stop.is_set():
                            break
                        self._push(self.diagnostics, f"Microfone: tentando {backend}")
                        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                        self._process = proc
                        try:
                            while not self._stop.is_set() and time.monotonic() - started < self.max_seconds:
                                if proc.stdout is None:
                                    break
                                # 320 bytes = 40 ms at 8 kHz G.711 A-law.
                                chunk = proc.stdout.read(320)
                                if not chunk:
                                    break
                                if len(chunk) < 320:
                                    chunk += b"\xd5" * (320 - len(chunk))
                                talk.send_talk_audio(chunk)
                                if not sent_any:
                                    sent_any = True
                                    chosen_backend = backend
                                    self._push(
                                        self.diagnostics,
                                        f"DVRIP 5/6 • áudio do microfone fluindo no socket de talk • {backend}",
                                    )
                                frames_sent += 1
                                bytes_sent += len(chunk)
                                if frames_sent % 25 == 0:
                                    drained = talk.drain_pending()
                                    if drained and frames_sent == 25:
                                        self._push(
                                            self.diagnostics,
                                            f"DVRIP talk • {drained} byte(s) downstream drenados sem bloquear",
                                        )
                                if frames_sent in {1, 25, 100} or frames_sent % 250 == 0:
                                    self._push(
                                        self.diagnostics,
                                        f"PTT envio • {frames_sent} frame(s) • {bytes_sent // 1024} KiB G.711A",
                                    )
                            if sent_any or self._stop.is_set():
                                break
                        finally:
                            _terminate_process_nonblocking(proc, grace=0.4)
                            if not sent_any and proc.stderr is not None:
                                try:
                                    err = proc.stderr.read(2048).decode("utf-8", "replace").strip()
                                except Exception:
                                    err = ""
                                if err:
                                    self._push(self.diagnostics, f"{backend}: {err[-800:]}")
                            self._process = None
                    if not sent_any and not self._stop.is_set():
                        self._push(self.status, "Microfone não forneceu áudio")
                    elif time.monotonic() - started >= self.max_seconds and not self._stop.is_set():
                        self._push(self.status, "PTT encerrado pelo limite de segurança")
                finally:
                    try:
                        # Stop belongs to the control channel. Its command
                        # sequence continues after the Claim/Start sequence.
                        control.talk_stop_no_reply()
                        self._push(
                            self.diagnostics,
                            f"DVRIP 6/6 • OPTalk Stop enviado no controle • {frames_sent} frame(s) • {chosen_backend or 'sem áudio'}",
                        )
                    except DvripError as exc:
                        self._push(self.diagnostics, f"Stop DVRIP: {exc}")
                    self._push(self.status, "Push-to-Talk encerrado")
            finally:
                talk.close()
                self._talk_session = None
                self._control_session = None



def _intelbras_http_connection(base_url: str, timeout: float = 4.0):
    parsed = urlparse(str(base_url or '').strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('base HTTP Intelbras inválida')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if parsed.scheme == 'https':
        return http.client.HTTPSConnection(
            parsed.hostname, port, timeout=max(1.0, float(timeout)),
            context=ssl._create_unverified_context(),
        )
    return http.client.HTTPConnection(parsed.hostname, port, timeout=max(1.0, float(timeout)))


def _digest_challenge_params(header: str) -> tuple[str, dict[str, str]]:
    raw = str(header or '').strip()
    if not raw:
        return '', {}
    scheme, _, value = raw.partition(' ')
    if scheme.casefold() != 'digest':
        return scheme, {}
    try:
        return 'Digest', {str(k): str(v) for k, v in parse_keqv_list(parse_http_list(value)).items()}
    except Exception:
        return 'Digest', {}


def _digest_hash(algorithm: str, value: str) -> str:
    alg = str(algorithm or 'MD5').upper().replace('_', '-')
    data = value.encode('utf-8')
    if alg.startswith('SHA-256'):
        return hashlib.sha256(data).hexdigest()
    return hashlib.md5(data).hexdigest()


def _digest_authorization(
    challenge: dict[str, str], username: str, password: str, method: str, uri: str,
    *, nonce_count: int = 1, cnonce: str = '',
) -> str:
    realm = str(challenge.get('realm') or '')
    nonce = str(challenge.get('nonce') or '')
    if not realm or not nonce:
        raise ValueError('desafio HTTP Digest incompleto')
    algorithm = str(challenge.get('algorithm') or 'MD5')
    qop_raw = str(challenge.get('qop') or '')
    qops = [item.strip().lower() for item in qop_raw.split(',') if item.strip()]
    qop = 'auth' if 'auth' in qops else (qops[0] if qops else '')
    cnonce = cnonce or os.urandom(8).hex()
    nc = f'{max(1, int(nonce_count)):08x}'
    ha1 = _digest_hash(algorithm, f'{username}:{realm}:{password}')
    if algorithm.upper().endswith('-SESS'):
        ha1 = _digest_hash(algorithm, f'{ha1}:{nonce}:{cnonce}')
    ha2 = _digest_hash(algorithm, f'{method}:{uri}')
    if qop:
        response = _digest_hash(algorithm, f'{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}')
    else:
        response = _digest_hash(algorithm, f'{ha1}:{nonce}:{ha2}')
    parts = [
        f'username="{username}"', f'realm="{realm}"', f'nonce="{nonce}"',
        f'uri="{uri}"', f'response="{response}"', f'algorithm={algorithm}',
    ]
    opaque = str(challenge.get('opaque') or '')
    if opaque:
        parts.append(f'opaque="{opaque}"')
    if qop:
        parts.extend([f'qop={qop}', f'nc={nc}', f'cnonce="{cnonce}"'])
    return 'Digest ' + ', '.join(parts)


def _intelbras_http_auth(base_url: str, username: str, password: str, timeout: float = 4.0) -> tuple[str, dict[str, str]]:
    """Get the device authentication challenge using a read-only CGI."""
    conn = _intelbras_http_connection(base_url, timeout)
    try:
        conn.request('GET', API_VERSION_PATH, headers={'User-Agent': f'Artin-Sentinel/{__version__}'})
        response = conn.getresponse()
        response.read(4096)
        if response.status == 200:
            return '', {}
        if response.status not in {401, 403}:
            raise ConnectionError(f'probe HTTP retornou {response.status}')
        header = str(response.getheader('WWW-Authenticate') or '')
        scheme, params = _digest_challenge_params(header)
        if scheme.casefold() == 'basic':
            return 'Basic', {}
        if scheme != 'Digest' or not params:
            raise PermissionError('equipamento não forneceu desafio HTTP Digest utilizável')
        return 'Digest', params
    finally:
        conn.close()


def _peek_http_status(conn, timeout: float = 0.0) -> tuple[int | None, str]:
    """Peek an HTTP response status without consuming the response bytes."""
    sock = getattr(conn, 'sock', None)
    if sock is None:
        return None, ''
    try:
        ready, _, _ = select.select([sock], [], [], max(0.0, float(timeout)))
        if not ready:
            return None, ''
        preview = sock.recv(768, socket.MSG_PEEK).decode('latin1', 'replace')
        first = preview.splitlines()[0] if preview else ''
        match = re.search(r'HTTP/\d(?:\.\d)?\s+(\d{3})', first)
        return (int(match.group(1)), first) if match else (None, first)
    except (OSError, ValueError):
        return None, ''


def _open_intelbras_postaudio_stream(
    base_url: str, username: str, password: str, *, audio_channel: int = 1,
    httptype: str = 'singlepart', timeout: float = 4.0,
):
    """Open the documented continuous ``postAudio`` request.

    The request advertises a deliberately large Content-Length and is stopped by
    closing the connection, matching the vendor HTTP API specification.  The
    caller owns and must close the returned connection.
    """
    httptype = 'multipart' if str(httptype).casefold() == 'multipart' else 'singlepart'
    scheme, challenge = _intelbras_http_auth(base_url, username, password, timeout)
    path = POST_AUDIO_PATH.format(channel=max(1, int(audio_channel)), httptype=httptype)
    authorization = ''
    if scheme == 'Digest':
        authorization = _digest_authorization(challenge, username, password, 'POST', path)
    elif scheme == 'Basic':
        token = base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
        authorization = 'Basic ' + token
    conn = _intelbras_http_connection(base_url, timeout)
    conn.putrequest('POST', path)
    conn.putheader('User-Agent', f'Artin-Sentinel/{__version__}')
    boundary = 'ArtinSentinelAudioBoundary'
    if httptype == 'multipart':
        conn.putheader('Content-Type', f'multipart/x-mixed-replace; boundary={boundary}')
    else:
        conn.putheader('Content-Type', 'Audio/G.711A')
    conn.putheader('Content-Length', '9999999')
    if authorization:
        conn.putheader('Authorization', authorization)
    conn.endheaders()

    # Authentication/protocol errors are normally returned immediately. Peek
    # without consuming a possible 200 response because some firmwares send the
    # success status before they finish consuming the long request body.
    code, first = _peek_http_status(conn, 0.18)
    if code is not None and code >= 400:
        conn.close()
        raise PermissionError(f'postAudio recusado pelo equipamento (HTTP {code})')
    return conn, scheme or 'none', boundary, code, first


def _format_postaudio_payload(chunk: bytes, httptype: str, boundary: str) -> bytes:
    if str(httptype).casefold() != 'multipart':
        return chunk
    return (
        f'--{boundary}\r\nContent-Type: Audio/G.711A\r\nContent-Length: {len(chunk)}\r\n\r\n'.encode('ascii')
        + chunk + b'\r\n'
    )


class IntelbrasHttpTalkbackSession:
    """Experimental official Intelbras HTTP ``postAudio`` talkback transport.

    This transport is exposed only after the same concrete firmware has passed
    the read-only HTTP API probe and reported at least one audio output.  Audio
    is captured locally as mono 8 kHz G.711 A-law and streamed to audio output
    channel 1 unless a future model profile proves another mapping.
    """

    def __init__(
        self, host: str, username: str, password: str, *, base_url: str = '',
        audio_channel: int = 1, microphone_backend: str = 'pulse',
        microphone_source: str = 'default', microphone_label: str = '',
        gain_db: int = 0, max_seconds: float = 18.0, framing_mode: str = 'auto',
    ):
        self.host = str(host or '')
        self.username = str(username or '')
        self.password = str(password or '')
        self.base_url = str(base_url or f'http://{self.host}').rstrip('/')
        self.audio_channel = max(1, int(audio_channel or 1))
        self.microphone_backend = str(microphone_backend or 'pulse').lower()
        self.microphone_source = str(microphone_source or 'default')
        self.microphone_label = str(microphone_label or self.microphone_source)
        self.gain_db = max(-6, min(int(gain_db), 9))
        self.max_seconds = max(3.0, min(float(max_seconds), 30.0))
        framing_mode = str(framing_mode or 'auto').casefold()
        self.framing_mode = framing_mode if framing_mode in {'auto', 'singlepart', 'multipart'} else 'auto'
        self.status: queue.Queue[str] = queue.Queue(maxsize=8)
        self.diagnostics: queue.Queue[str] = queue.Queue(maxsize=24)
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._connection = None
        # Field MHDX testing showed the recorder can keep its audio resource busy
        # briefly after postAudio closes. The UI may use this before resuming listen.
        self.resume_delay_ms = 3000

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    @property
    def available(self) -> bool:
        return bool(shutil.which('ffmpeg') and self.microphone_backend in {'pulse', 'alsa'})

    def _push(self, q: queue.Queue[str], text: str) -> None:
        text = sanitize_talkback_diagnostic(text, self.username, self.password)
        if not text:
            return
        while True:
            try:
                q.put_nowait(text); return
            except queue.Full:
                try: q.get_nowait()
                except queue.Empty: return

    def latest_status(self) -> str | None:
        latest = None
        while True:
            try: latest = self.status.get_nowait()
            except queue.Empty: return latest

    def drain_diagnostics(self) -> list[str]:
        out = []
        while True:
            try: out.append(self.diagnostics.get_nowait())
            except queue.Empty: return out

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear(); self._finished.clear()
        self._thread = threading.Thread(target=self._run_wrapper, name='sentinel-talkback-intelbras-http', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        _terminate_process_nonblocking(self._process)
        conn = self._connection
        if conn is not None:
            try: conn.close()
            except Exception: pass

    def _capture_commands(self) -> list[tuple[str, list[str]]]:
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            return []
        backends = ffmpeg_microphone_inputs()
        gain_filter = ['-af', f'volume={self.gain_db}dB'] if self.gain_db else []
        common_out = [*gain_filter, '-ac', '1', '-ar', '8000', '-c:a', 'pcm_alaw', '-f', 'alaw', 'pipe:1']
        commands: list[tuple[str, list[str]]] = []
        def add(backend: str, source: str, label: str) -> None:
            if backend not in backends:
                return
            commands.append((label, [
                ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-thread_queue_size', '512',
                '-f', backend, '-i', source, *common_out,
            ]))
        add(self.microphone_backend, self.microphone_source, self.microphone_label or self.microphone_backend)
        if self.microphone_backend == 'pulse' and self.microphone_source != 'default':
            add('pulse', 'default', 'Pulse/PipeWire padrão (fallback)')
        if self.microphone_backend != 'alsa':
            add('alsa', 'default', 'ALSA padrão (fallback)')
        return commands

    def _run_wrapper(self) -> None:
        try:
            self._run()
        except Exception as exc:
            if not self._stop.is_set():
                self._push(self.status, f'Push-to-Talk falhou: {type(exc).__name__}')
            self._push(self.diagnostics, f'{type(exc).__name__}: {exc}')
        finally:
            self._finished.set()

    def _start_buffer_probe(self, result_queue: queue.Queue) -> None:
        def worker():
            result = query_talkback_buffer_empty(
                self.base_url, self.username, self.password,
                audio_channel=self.audio_channel, timeout=1.4,
            )
            try:
                result_queue.put_nowait(result)
            except queue.Full:
                pass
        threading.Thread(target=worker, name='sentinel-intelbras-audio-buffer-probe', daemon=True).start()

    def _run_framing_attempt(self, httptype: str, commands: list[tuple[str, list[str]]]) -> dict:
        conn, auth_scheme, boundary, initial_code, initial_line = _open_intelbras_postaudio_stream(
            self.base_url, self.username, self.password,
            audio_channel=self.audio_channel, httptype=httptype, timeout=4.0,
        )
        self._connection = conn
        self._push(self.diagnostics, f'HTTP 1/6 • autenticação {auth_scheme} preparada')
        self._push(
            self.diagnostics,
            f'HTTP 2/6 • postAudio aberto • {httptype} • saída de áudio {self.audio_channel} • G.711A'
            + (f' • resposta antecipada HTTP {initial_code}' if initial_code else ''),
        )
        if initial_line and initial_code:
            self._push(self.diagnostics, f'Resposta HTTP inicial • {initial_line}')

        started = time.monotonic()
        frames_sent = 0
        bytes_sent = 0
        chosen_backend = ''
        sent_any = False
        stable_reported = False
        decoder_confirmed = False
        buffer_probe_started = False
        buffer_probe_reported = False
        buffer_results: queue.Queue = queue.Queue(maxsize=1)
        attempt_error: Exception | None = None

        try:
            for backend, cmd in commands:
                if self._stop.is_set():
                    break
                self._push(self.diagnostics, f'Microfone: tentando {backend}')
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                self._process = proc
                try:
                    while not self._stop.is_set() and time.monotonic() - started < self.max_seconds:
                        if proc.stdout is None:
                            break
                        # V3.81 illustrates 800-byte G.711A parts in multipart.
                        # Using the same 100 ms payload size in singlepart makes
                        # transport comparisons deterministic without changing
                        # the 8 kHz mono A-law encoding.
                        chunk = proc.stdout.read(800)
                        if not chunk:
                            break
                        if len(chunk) < 800:
                            chunk += b'\xd5' * (800 - len(chunk))
                        payload = _format_postaudio_payload(chunk, httptype, boundary)
                        try:
                            conn.send(payload)
                        except (OSError, http.client.HTTPException) as exc:
                            if self._stop.is_set():
                                break
                            code, line = _peek_http_status(conn, 0.0)
                            if code:
                                self._push(self.diagnostics, f'Resposta HTTP antes da queda • {line or code}')
                            attempt_error = exc
                            break

                        if not sent_any:
                            sent_any = True
                            chosen_backend = backend
                            self._push(self.status, 'Transmitindo • aguardando confirmação do equipamento')
                            self._push(self.diagnostics, f'HTTP 3/6 • áudio do microfone saindo do PC • {backend}')
                        frames_sent += 1
                        bytes_sent += len(chunk)
                        if frames_sent in {1, 10, 50, 100} or frames_sent % 250 == 0:
                            self._push(self.diagnostics, f'PTT envio • {frames_sent} frame(s) • {bytes_sent // 1024} KiB G.711A • {httptype}')

                        if frames_sent >= 4 and not buffer_probe_started:
                            buffer_probe_started = True
                            self._start_buffer_probe(buffer_results)

                        if buffer_probe_started and not buffer_probe_reported:
                            try:
                                flag, detail = buffer_results.get_nowait()
                            except queue.Empty:
                                pass
                            else:
                                buffer_probe_reported = True
                                if flag is False:
                                    decoder_confirmed = True
                                    self._push(self.diagnostics, f'HTTP 4/6 • decoder confirmou dados de talkback • {detail}')
                                    self._push(self.status, 'Falando • buffer de talkback ativo')
                                elif flag is True:
                                    self._push(self.diagnostics, f'HTTP 4/6 • decoder consultado • {detail}')
                                else:
                                    self._push(self.diagnostics, f'HTTP 4/6 • diagnóstico do decoder indisponível • {detail}')

                        elapsed = time.monotonic() - started
                        if elapsed >= 1.5 and not stable_reported:
                            stable_reported = True
                            code, line = _peek_http_status(conn, 0.0)
                            extra = f' • resposta HTTP {code}' if code else ''
                            self._push(self.diagnostics, f'HTTP 5/6 • sessão permaneceu aberta por {elapsed:.1f}s{extra}')
                            if line and code:
                                self._push(self.diagnostics, f'Resposta HTTP observada • {line}')
                            if not decoder_confirmed:
                                self._push(self.status, 'Transmitindo • sessão HTTP estável')

                    if attempt_error is not None or sent_any or self._stop.is_set():
                        break
                finally:
                    _terminate_process_nonblocking(proc, grace=0.4)
                    if not sent_any and proc.stderr is not None:
                        try:
                            err = proc.stderr.read(2048).decode('utf-8', 'replace').strip()
                        except Exception:
                            err = ''
                        if err:
                            self._push(self.diagnostics, f'{backend}: {err[-800:]}')
                    self._process = None

            if buffer_probe_started and not buffer_probe_reported:
                try:
                    flag, detail = buffer_results.get(timeout=0.15)
                except queue.Empty:
                    self._push(self.diagnostics, 'HTTP 4/6 • consulta do buffer ainda sem resposta quando a sessão terminou')
                else:
                    buffer_probe_reported = True
                    if flag is False:
                        decoder_confirmed = True
                        self._push(self.diagnostics, f'HTTP 4/6 • decoder confirmou dados de talkback • {detail}')
                    elif flag is True:
                        self._push(self.diagnostics, f'HTTP 4/6 • decoder consultado • {detail}')
                    else:
                        self._push(self.diagnostics, f'HTTP 4/6 • diagnóstico do decoder indisponível • {detail}')
            elif not buffer_probe_started:
                self._push(self.diagnostics, 'HTTP 4/6 • buffer não consultado • sessão encerrou antes da janela de diagnóstico')

            if not stable_reported:
                self._push(self.diagnostics, f'HTTP 5/6 • sessão não estabilizou • {time.monotonic() - started:.1f}s')
            if not sent_any and not self._stop.is_set() and attempt_error is None:
                self._push(self.status, 'Microfone não forneceu áudio')
        finally:
            try:
                code, line = _peek_http_status(conn, 0.0)
                if code:
                    self._push(self.diagnostics, f'Resposta HTTP final observada • {line or code}')
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            self._connection = None
            self._push(
                self.diagnostics,
                f'HTTP 6/6 • postAudio encerrado • {frames_sent} frame(s) • {bytes_sent // 1024} KiB • '
                f'{httptype} • {chosen_backend or "sem áudio"}',
            )

        return {
            'error': attempt_error,
            'frames': frames_sent,
            'bytes': bytes_sent,
            'elapsed': time.monotonic() - started,
            'stable': stable_reported,
            'decoder_confirmed': decoder_confirmed,
            'sent_any': sent_any,
            'httptype': httptype,
        }

    def _run(self) -> None:
        commands = self._capture_commands()
        if not commands:
            self._push(self.status, 'Microfone local indisponível no FFmpeg')
            return
        self._push(self.status, 'Conectando MIC • Intelbras HTTP')
        modes = [self.framing_mode] if self.framing_mode != 'auto' else ['singlepart', 'multipart']
        last_error: Exception | None = None
        for pos, mode in enumerate(modes):
            if self._stop.is_set():
                break
            if pos:
                self._push(self.status, 'Tentando compatibilidade multipart • Intelbras HTTP')
                self._push(self.diagnostics, 'Fallback HTTP • singlepart encerrou cedo; tentando multipart V3.81 com blocos de 800 bytes')
            result = self._run_framing_attempt(mode, commands)
            last_error = result['error']
            if self._stop.is_set():
                break
            if last_error is None:
                if time.monotonic() and result['elapsed'] >= self.max_seconds:
                    self._push(self.status, 'PTT encerrado pelo limite de segurança')
                break
            # A peer reset/broken pipe in the first seconds is exactly the field
            # symptom seen on iMX C. In auto mode, use the vendor-documented
            # multipart framing before declaring transport failure.
            early_peer_close = isinstance(last_error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError))
            if mode == 'singlepart' and self.framing_mode == 'auto' and early_peer_close and result['elapsed'] < 3.0:
                self._push(self.diagnostics, f'singlepart encerrado pelo equipamento após {result["frames"]} frame(s): {type(last_error).__name__}')
                continue
            raise last_error
        self._push(self.status, 'Push-to-Talk encerrado')


def read_audio_packet(stream, size: int, stop_event, deadline: float | None = None) -> bytes:
    """Assemble a complete raw FFmpeg packet without dropping short pipe reads."""
    payload = bytearray()
    while len(payload) < size and not stop_event.is_set():
        if deadline is not None and time.monotonic() >= deadline:
            break
        chunk = stream.read(size - len(payload))
        if not chunk:
            break
        payload.extend(chunk)
    return bytes(payload) if len(payload) == size else b""


class IntelbrasNetSDKTalkbackSession:
    """Experimental direct-camera talkback through the official Intelbras NetSDK.

    0.2.42 reproduces the official Linux 05.Talk setup literally and isolates
    the two remaining speaker parameters as controlled field variants.  The
    reference file remains untouched; live PCM/G.711A are kept only as follow-up
    checks after the speaker handshake is proven.
    """

    # The official Linux demo ships localRecordAudio.dav as 648-byte packets:
    # an invariant 8-byte NetSDK audio prefix plus 640 bytes of PCM s16le
    # (40 ms at 8 kHz mono).
    PCM_FRAME_PREFIX = bytes.fromhex("00 00 01 f0 0c 02 80 02")
    PCM_PAYLOAD_BYTES = 640
    G711A_PAYLOAD_BYTES = 320
    G711A_FRAME_BASE = bytes.fromhex("00 00 01 f0 0e 02")

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        candidate_ports: list[int] | tuple[int, ...] = (37777, 37778),
        microphone_backend: str = "pulse",
        microphone_source: str = "default",
        microphone_label: str = "",
        gain_db: int = 0,
        max_seconds: float = 18.0,
        channel_index: int = 0,
        test_mode: str = "literal-reference",
    ):
        self.host = str(host or "")
        self.username = str(username or "")
        self.password = str(password or "")
        ports: list[int] = []
        for raw in candidate_ports or ():
            try:
                port = int(raw)
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in ports:
                ports.append(port)
        for fallback in (37777, 37778):
            if fallback not in ports:
                ports.append(fallback)
        self.candidate_ports = ports
        self.microphone_backend = str(microphone_backend or "pulse").lower()
        self.microphone_source = str(microphone_source or "default")
        self.microphone_label = str(microphone_label or self.microphone_source)
        self.gain_db = max(-6, min(int(gain_db), 9))
        self.max_seconds = max(3.0, min(float(max_seconds), 30.0))
        self.channel_index = max(0, int(channel_index or 0))
        normalized_mode = str(test_mode or "literal-reference").strip().lower()
        if normalized_mode not in {"literal-reference", "literal-reference-wait", "literal-reference-speaker1", "live-pcm-literal", "live-g711a-server"}:
            normalized_mode = "literal-reference"
        self.test_mode = normalized_mode
        self.status: queue.Queue[str] = queue.Queue(maxsize=8)
        self.diagnostics: queue.Queue[str] = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._sdk = None
        self._login_handle = 0
        self._talk_handle = 0
        self._audio_callback = None
        self.resume_delay_ms = 900

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    @property
    def available(self) -> bool:
        return bool(netsdk_runtime_info().available and shutil.which("ffmpeg"))

    def _push(self, q: queue.Queue[str], text: str) -> None:
        text = sanitize_talkback_diagnostic(text, self.username, self.password)
        if not text:
            return
        while True:
            try:
                q.put_nowait(text)
                return
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    return

    def latest_status(self) -> str | None:
        latest = None
        while True:
            try:
                latest = self.status.get_nowait()
            except queue.Empty:
                return latest

    def drain_diagnostics(self) -> list[str]:
        out = []
        while True:
            try:
                out.append(self.diagnostics.get_nowait())
            except queue.Empty:
                return out

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._finished.clear()
        self._thread = threading.Thread(target=self._run_wrapper, name="sentinel-talkback-intelbras-netsdk", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        _terminate_process_nonblocking(self._process)

    def _capture_commands(self, codec: str = "pcm") -> list[tuple[str, list[str]]]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return []
        backends = ffmpeg_microphone_inputs()
        gain_filter = ["-af", f"volume={self.gain_db}dB"] if self.gain_db else []
        if codec == "g711a":
            common_out = [*gain_filter, "-ac", "1", "-ar", "8000", "-c:a", "pcm_alaw", "-f", "alaw", "pipe:1"]
        else:
            common_out = [*gain_filter, "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"]
        commands: list[tuple[str, list[str]]] = []

        def add(backend: str, source: str, label: str) -> None:
            if backend not in backends:
                return
            commands.append((label, [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-thread_queue_size", "512", "-f", backend, "-i", source, *common_out,
            ]))

        add(self.microphone_backend, self.microphone_source, self.microphone_label or self.microphone_backend)
        if self.microphone_backend == "pulse" and self.microphone_source != "default":
            add("pulse", "default", "Pulse/PipeWire padrão (fallback)")
        if self.microphone_backend != "alsa":
            add("alsa", "default", "ALSA padrão (fallback)")
        return commands

    @staticmethod
    def _private_audio_frame(payload: bytes, codec: str) -> bytes:
        if codec == "g711a":
            prefix = IntelbrasNetSDKTalkbackSession.G711A_FRAME_BASE
        else:
            prefix = IntelbrasNetSDKTalkbackSession.PCM_FRAME_PREFIX[:6]
        length = len(payload)
        return prefix + bytes((length & 0xFF, (length >> 8) & 0xFF)) + payload

    def _mode_description(self) -> tuple[str, str, TalkFormat, str, bool, int]:
        # A1 is byte-for-byte/reference-file compatible with the official Linux
        # 05.Talk sample, including the *zero* packet period left by memset().
        if self.test_mode == "literal-reference-wait":
            return "TESTE A2 • demo literal + aguardar dispositivo", "reference", TalkFormat(DH_TALK_PCM, 8000, 16, 0), "server", True, 0
        if self.test_mode == "literal-reference-speaker1":
            return "TESTE A3 • demo literal + speaker 1", "reference", TalkFormat(DH_TALK_PCM, 8000, 16, 0), "server", False, 1
        if self.test_mode == "live-pcm-literal":
            return "TESTE B • C270 PCM com handshake literal", "pcm", TalkFormat(DH_TALK_PCM, 8000, 16, 0), "server", False, 0
        if self.test_mode == "live-g711a-server":
            return "TESTE C • C270 G.711A 8 kHz", "g711a", TalkFormat(DH_TALK_G711A, 8000, 16, 0), "server", False, 0
        return "TESTE A1 • demo 05.Talk literal", "reference", TalkFormat(DH_TALK_PCM, 8000, 16, 0), "server", False, 0

    def _run_wrapper(self) -> None:
        try:
            self._run()
        except Exception as exc:
            if not self._stop.is_set():
                self._push(self.status, f"Push-to-Talk falhou: {type(exc).__name__}")
            self._push(self.diagnostics, f"{type(exc).__name__}: {exc}")
        finally:
            self._cleanup()
            self._finished.set()

    def _cleanup(self) -> None:
        _terminate_process_nonblocking(self._process)
        self._process = None
        sdk = self._sdk
        if sdk is None:
            return
        if self._talk_handle:
            try:
                sdk.lib.CLIENT_StopTalkEx(int(self._talk_handle))
            except Exception:
                pass
            self._talk_handle = 0
        if self._login_handle:
            try:
                sdk.logout(int(self._login_handle))
            except Exception:
                pass
            self._login_handle = 0

    def _run(self) -> None:
        info = netsdk_runtime_info()
        if not info.available:
            raise NetSDKUnavailable(info.detail)

        test_label, source_kind, chosen, sdk_mode, enable_wait, speaker_channel = self._mode_description()
        commands = [] if source_kind == "reference" else self._capture_commands("g711a" if source_kind == "g711a" else "pcm")
        if source_kind != "reference" and not commands:
            raise RuntimeError("FFmpeg não encontrou uma entrada de microfone Pulse/PipeWire ou ALSA")
        reference = reference_audio_path()
        if source_kind == "reference" and not reference.is_file():
            raise RuntimeError("áudio de referência 05.Talk ausente; importe novamente o ZIP oficial em Configuração → Atualizações")

        self._push(self.status, f"Conectando MIC • {test_label}")
        self._push(self.diagnostics, f"SDK 1/8 • runtime oficial carregável • {info.architecture} • {test_label}")
        sdk = IntelbrasNetSDK.instance()
        self._sdk = sdk

        login = None
        failures = []
        for port in self.candidate_ports:
            if self._stop.is_set():
                return
            result = sdk.login(self.host, port, self.username, self.password)
            if result.handle:
                login = result
                break
            failures.append(f"{port}:0x{int(result.error_code):08x}")
        if login is None:
            detail = ", ".join(failures[:4]) or "sem porta candidata"
            raise ConnectionError(f"NetSDK não autenticou no dispositivo ({detail})")
        self._login_handle = int(login.handle)
        protocol_type = sdk.get_protocol_type(self._login_handle)
        protocol_label = {0: "desconhecido", 1: "V2", 2: "V3"}.get(protocol_type, str(protocol_type))
        self._push(
            self.diagnostics,
            f"SDK 2/8 • login direto OK • TCP {login.port}"
            + (f" • {login.channels} canal(is)" if login.channels else "")
            + f" • protocolo talk {protocol_label}",
        )

        formats = sdk.query_talk_formats(self._login_handle)
        if formats:
            names = ", ".join(f"{item.name}/{item.sample_rate or '?'}Hz/{item.audio_bits or '?'}bit" for item in formats[:8])
            self._push(self.diagnostics, f"SDK 3/8 • codecs anunciados: {names}")
        else:
            self._push(self.diagnostics, "SDK 3/8 • lista de codecs indisponível")

        # MODE3 is deliberately a separate field-test option. On V3 devices it
        # follows the vendor Intelligent Building manual; server mode remains
        # the exact Linux 05.Talk sample path.
        audio_port = 0
        if sdk_mode == "v3":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind(("0.0.0.0", 0))
                audio_port = int(sock.getsockname()[1])
        def setup_step(text: str) -> None:
            self._push(self.diagnostics, f"SDK SETUP • {text}")

        ok, detail = sdk.configure_direct_talk(
            self._login_handle, chosen, self.channel_index, mode=sdk_mode,
            protocol_type=protocol_type, audio_port=audio_port,
            speaker_channel=speaker_channel, enable_wait=enable_wait, transfer=False,
            step_callback=setup_step,
        )
        if not ok:
            raise RuntimeError(f"NetSDK não configurou talk direto: {detail}")
        codec_label = "G.711A" if chosen.encode_type == DH_TALK_G711A else "PCM"
        mode_label = "V3/MODE3" if sdk_mode == "v3" else "SERVER_MODE"
        self._push(
            self.diagnostics,
            f"SDK 4/8 • {test_label} • {mode_label} • {codec_label} 8000 Hz • "
            f"packetPeriod={chosen.packet_period_ms} • speaker={speaker_channel} • wait={'true' if enable_wait else 'false'}",
        )

        remote_frames = 0
        remote_first = ""
        CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_ubyte, ctypes.c_long)

        def audio_callback(_talk_handle, data_ptr, size, audio_flag, _user):
            nonlocal remote_frames, remote_first
            if self._stop.is_set() or not data_ptr or int(size) <= 0:
                return
            if int(audio_flag) == 1:
                remote_frames += 1
                if not remote_first:
                    try:
                        raw = ctypes.string_at(data_ptr, min(int(size), 12))
                        remote_first = f"{int(size)} B • {raw.hex(' ')}"
                    except Exception:
                        remote_first = f"{int(size)} B"

        self._audio_callback = CALLBACK(audio_callback)
        callback_ptr = ctypes.cast(self._audio_callback, ctypes.c_void_p)
        sdk.lib.CLIENT_StartTalkEx.argtypes = [ctypes.c_long, ctypes.c_void_p, ctypes.c_long]
        talk_handle = int(sdk.lib.CLIENT_StartTalkEx(self._login_handle, callback_ptr, 0) or 0)
        if not talk_handle:
            raise RuntimeError(f"CLIENT_StartTalkEx falhou (0x{sdk.last_error():08x})")
        self._talk_handle = talk_handle
        self._push(self.diagnostics, "SDK 5/8 • CLIENT_StartTalkEx aceito")

        frames_sent = 0
        bytes_sent = 0
        send_failures = 0
        selected_label = ""
        started = time.monotonic()

        def send_frame(frame: bytes, label: str) -> bool:
            nonlocal frames_sent, bytes_sent, send_failures
            buf = ctypes.create_string_buffer(frame, len(frame))
            sent = int(sdk.lib.CLIENT_TalkSendData(int(self._talk_handle), buf, len(frame)))
            if sent > 0:
                frames_sent += 1
                bytes_sent += sent
                if frames_sent == 1:
                    self._push(self.status, f"Transmitindo • {test_label}")
                    self._push(self.diagnostics, f"SDK 7/8 • primeiro pacote enviado • {sent} bytes • {label}")
                elif frames_sent in {10, 50, 100, 250} or frames_sent % 500 == 0:
                    self._push(self.diagnostics, f"NetSDK envio • {frames_sent} pacote(s) • {bytes_sent // 1024} KiB • {test_label}")
                return True
            send_failures += 1
            if send_failures <= 3:
                self._push(self.diagnostics, f"TalkSendData recusou pacote • retorno {sent} • erro 0x{sdk.last_error():08x}")
            return False

        if source_kind == "reference":
            selected_label = "localRecordAudio.dav oficial"
            self._push(self.diagnostics, f"SDK 6/8 • enviando referência original do demo 05.Talk • {reference.name}")
            raw = reference.read_bytes()
            frame_size = 648
            if len(raw) < frame_size or len(raw) % frame_size != 0:
                raise RuntimeError(f"arquivo de referência inválido ({len(raw)} bytes)")
            offset = 0
            next_deadline = time.monotonic()
            while not self._stop.is_set() and time.monotonic() - started < self.max_seconds:
                if offset >= len(raw):
                    offset = 0
                frame = raw[offset:offset + frame_size]
                offset += frame_size
                if not send_frame(frame, selected_label) and send_failures >= 5:
                    break
                next_deadline += 0.041
                delay = next_deadline - time.monotonic()
                if delay > 0:
                    time.sleep(min(delay, 0.041))
        else:
            payload_bytes = self.G711A_PAYLOAD_BYTES if source_kind == "g711a" else self.PCM_PAYLOAD_BYTES
            for label, cmd in commands:
                if self._stop.is_set():
                    break
                selected_label = label
                self._push(self.diagnostics, f"SDK 6/8 • {test_label} • microfone: tentando {label} • ganho {self.gain_db:+d} dB")
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                self._process = proc
                if proc.stdout is None:
                    _terminate_process_nonblocking(proc)
                    continue
                first_deadline = time.monotonic() + 2.4
                got_first = False
                next_deadline = time.monotonic()
                while not self._stop.is_set() and time.monotonic() - started < self.max_seconds:
                    payload = read_audio_packet(
                        proc.stdout, payload_bytes, self._stop,
                        first_deadline if not got_first else None,
                    )
                    if not payload:
                        break
                    got_first = True
                    frame = self._private_audio_frame(payload, source_kind)
                    if not send_frame(frame, label) and send_failures >= 5:
                        break
                    next_deadline = max(next_deadline + 0.040, time.monotonic())
                    delay = next_deadline - time.monotonic()
                    if delay > 0:
                        time.sleep(min(delay, 0.040))
                _terminate_process_nonblocking(proc)
                self._process = None
                if got_first or frames_sent:
                    break

        duration = max(0.0, time.monotonic() - started)
        if frames_sent:
            extra = f" • retorno {remote_frames} pacote(s)" if remote_frames else ""
            if remote_first:
                extra += f" • primeiro retorno {remote_first}"
            self._push(
                self.diagnostics,
                f"SDK 8/8 • {test_label} encerrado • {frames_sent} pacote(s) • {bytes_sent // 1024} KiB • {duration:.1f}s"
                + extra + (f" • {selected_label}" if selected_label else ""),
            )
            self._push(self.status, "Push-to-Talk encerrado")
        else:
            self._push(self.diagnostics, f"SDK 8/8 • {test_label} sem áudio enviado • {duration:.1f}s • falhas {send_failures}")
            if not self._stop.is_set():
                self._push(self.status, "NetSDK abriu talk, mas não conseguiu enviar áudio")

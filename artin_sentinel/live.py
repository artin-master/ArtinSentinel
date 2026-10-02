from __future__ import annotations

import os
import json
import queue
import re
from functools import lru_cache
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlparse, urlunparse

from .xm_dvrip import DvripSession, DvripError


FRAME_WIDTH = 640
FRAME_HEIGHT = 360
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT * 3


@lru_cache(maxsize=1)
def ffmpeg_rtsp_timeout_args() -> tuple[str, ...]:
    """Return a timeout option supported by the local FFmpeg RTSP demuxer.

    Fedora/FFmpeg builds seen in the field may reject the generic
    ``-rw_timeout`` option when it is placed before an RTSP input, even though
    libavformat documents it globally.  RTSP itself exposes ``-timeout`` (in
    microseconds), which is the preferred option here.  Older builds may expose
    ``-stimeout``.  If neither is advertised, omit the CLI timeout entirely and
    rely on cooperative process termination/reconnect instead of making Live
    View fail before opening the stream.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return ()
    try:
        cp = subprocess.run(
            [ffmpeg, "-hide_banner", "-h", "demuxer=rtsp"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        help_text = f"{cp.stdout}\n{cp.stderr}"
    except (OSError, subprocess.TimeoutExpired):
        help_text = ""
    if re.search(r"(?m)^\s*-timeout\s", help_text):
        return ("-timeout", "5000000")
    if re.search(r"(?m)^\s*-stimeout\s", help_text):
        return ("-stimeout", "5000000")
    # Modern FFmpeg RTSP demuxers use -timeout.  If help discovery itself is
    # unavailable, prefer the RTSP-specific option rather than rw_timeout.
    if not help_text:
        return ("-timeout", "5000000")
    return ()


def authenticated_rtsp_url(url: str, username: str, password: str) -> str:
    # Some OEM cameras encode credentials in the RTSP path. Persist only a
    # {username}/{password} template and materialize it in memory at runtime.
    if "{username}" in (url or "") or "{password}" in (url or ""):
        return (url or "").replace("{username}", quote(username or "", safe="")).replace("{password}", quote(password or "", safe=""))
    parsed = urlparse(url)
    if not parsed.hostname:
        return url
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    auth = ""
    if username:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    netloc = f"{auth}{host}{port}"
    return urlunparse((parsed.scheme or "rtsp", netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def sanitize_text(text: str) -> str:
    """Best-effort removal of secrets from FFmpeg/RTSP diagnostics."""
    if not text:
        return ""
    text = re.sub(r"(rtsp://)[^/@\s]+@", r"\1***:***@", text, flags=re.I)
    text = re.sub(r"(Authorization:\s*)(.+)", r"\1<redacted>", text, flags=re.I)
    text = re.sub(r"(password[=_])[^_&\s/?]+", r"\1<redacted>", text, flags=re.I)
    text = re.sub(r"(_password_)[^_&\s/?]+", r"\1<redacted>", text, flags=re.I)
    return text.strip()



def _low_value_ffmpeg_warning(text: str) -> bool:
    """Hide noisy FFmpeg warnings from the operator-facing diagnostic history."""
    lowered = str(text or "").lower()
    return any(token in lowered for token in (
        "non-monotonic dts",
        "deprecated pixel format used",
    ))


def _transient_rtsp_error(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in (
        "503", "service unavailable", "server returned 5xx", "server error reply",
    ))



def _network_failure_reason(text: str) -> str:
    """Classify transport errors that cannot be fixed by changing RTSP profile.

    These messages come from the OS/socket layer. When one is present, trying
    Main/Sub and TCP/UDP against the same host only creates noise and load.
    """
    lowered = str(text or "").casefold()
    patterns = (
        ("no route to host", "sem rota até o host"),
        ("network is unreachable", "rede inacessível"),
        ("network unreachable", "rede inacessível"),
        ("host is unreachable", "host inacessível"),
        ("destination host unreachable", "host inacessível"),
        ("network is down", "interface/rede indisponível"),
    )
    for token, label in patterns:
        if token in lowered:
            return label
    return ""


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    ok: bool = False
    video_codec: str = ""
    video_width: int = 0
    video_height: int = 0
    audio_codec: str = ""
    audio_sample_rate: int = 0
    audio_channels: int = 0
    detail: str = ""
    error_code: str = ""
    video_present: bool | None = None
    audio_present: bool | None = None

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_codec)


@lru_cache(maxsize=1)
def ffmpeg_decoders() -> frozenset[str]:
    """Return decoder names announced by the local FFmpeg build."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return frozenset()
    try:
        cp = subprocess.run(
            [ffmpeg, "-hide_banner", "-decoders"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    names: set[str] = set()
    for line in (cp.stdout or "").splitlines():
        match = re.match(r"^\s*[A-Z\.]{6}\s+([A-Za-z0-9_\-]+)\s", line)
        if match:
            names.add(match.group(1).lower())
    return frozenset(names)


def local_decoder_available(codec: str) -> bool:
    codec = (codec or "").strip().lower()
    aliases = {
        "h265": "hevc",
        "h.265": "hevc",
        "h.265+": "hevc",
        "h264": "h264",
        "h.264": "h264",
        "h.264+": "h264",
        "g711u": "pcm_mulaw",
        "g.711u": "pcm_mulaw",
        "pcmu": "pcm_mulaw",
        "g711a": "pcm_alaw",
        "g.711a": "pcm_alaw",
        "pcma": "pcm_alaw",
    }
    wanted = aliases.get(codec, codec)
    decoders = ffmpeg_decoders()
    if wanted in decoders:
        return True
    # Hardware wrappers can still decode on a supported host, but the software
    # decoder is preferred for the compatibility gate.
    return any(name.startswith(wanted + "_") for name in decoders)


@lru_cache(maxsize=1)
def ffmpeg_audio_output_devices() -> frozenset[str]:
    """Return audio output device muxers advertised by the local FFmpeg build."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return frozenset()
    try:
        cp = subprocess.run(
            [ffmpeg, "-hide_banner", "-devices"],
            capture_output=True, text=True, timeout=3.0, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    result: set[str] = set()
    for line in (cp.stdout or "").splitlines():
        # Typical layouts are `` E alsa`` or `` DE pulse`` depending on build.
        match = re.match(r"^\s*([D\. ])([E\. ])\s+([A-Za-z0-9_\-]+)\s", line)
        if match and match.group(2) == "E":
            result.add(match.group(3).lower())
            continue
        match = re.match(r"^\s*E\s+([A-Za-z0-9_\-]+)\s", line)
        if match:
            result.add(match.group(1).lower())
    return frozenset(result)


def local_media_status() -> dict[str, object]:
    """Small, serializable multimedia capability summary for diagnostics."""
    outputs = ffmpeg_audio_output_devices()
    return {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "ffplay": bool(shutil.which("ffplay")),
        "audio_output_pulse": "pulse" in outputs,
        "audio_output_alsa": "alsa" in outputs,
        "dynamic_audio_volume": bool(shutil.which("pactl")),
        "h264": local_decoder_available("h264"),
        "hevc": local_decoder_available("hevc"),
        "aac": local_decoder_available("aac"),
        "g711u": local_decoder_available("pcm_mulaw"),
        "g711a": local_decoder_available("pcm_alaw"),
    }


def classify_media_probe_error(error: str) -> tuple[str, str]:
    """Map FFmpeg errors to controlled labels; never return external text/URLs."""
    text = str(error or "").casefold()
    groups = (
        ("authentication", "Autenticação rejeitada ou necessária", ("401", "403", "unauthorized", "forbidden", "authentication failed")),
        ("codec_unsupported", "Codec não suportado pelo decoder local", ("unknown decoder", "decoder not found", "unsupported codec", "no decoder")),
        ("stream_not_found", "Stream não encontrado", ("404", "not found", "454", "session not found")),
        ("timeout", "Tempo limite na verificação do stream", ("timed out", "timeout")),
        ("rtsp_unavailable", "RTSP/rede indisponível", ("connection refused", "connection reset", "no route to host", "network is unreachable", "503", "service unavailable")),
        ("invalid_response", "Resposta de mídia inválida", ("invalid data found", "invalid response")),
    )
    for code, detail, tokens in groups:
        if any(token in text for token in tokens):
            return code, detail
    return "other_error", "Não foi possível confirmar a mídia"


def probe_rtsp_media_capabilities(
    url: str,
    username: str = "",
    password: str = "",
    *,
    transport: str = "tcp",
    timeout: float = 8.0,
) -> MediaProbeResult:
    """Inspect video/audio tracks with ffprobe without persisting credentials."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not url:
        return MediaProbeResult(detail="ffprobe não disponível" if not ffprobe else "Rota não configurada",
                                error_code="probe_unavailable" if not ffprobe else "stream_not_found")
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
            raise ValueError("Invalid RTSP route")
        auth_url = authenticated_rtsp_url(url, username, password)
    except (ValueError, TypeError):
        return MediaProbeResult(detail="Rota RTSP inválida", error_code="invalid_response")
    cmd = [
        ffprobe,
        "-v", "error",
        "-rtsp_transport", transport,
        *list(ffmpeg_rtsp_timeout_args()),
        "-show_streams",
        "-of", "json",
        auth_url,
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return MediaProbeResult(detail="Tempo limite na verificação do stream", error_code="timeout")
    except OSError:
        return MediaProbeResult(detail="Não foi possível executar ffprobe", error_code="probe_unavailable")
    if cp.returncode != 0:
        code, detail = classify_media_probe_error(cp.stderr or "")
        return MediaProbeResult(detail=detail, error_code=code)
    try:
        payload = json.loads(cp.stdout or "{}")
        streams = payload.get("streams", [])
        if not isinstance(streams, list) or not all(isinstance(st, dict) for st in streams):
            raise ValueError("Invalid streams")
    except (ValueError, AttributeError):
        return MediaProbeResult(detail="ffprobe retornou resposta inválida", error_code="invalid_response")
    video = next((st for st in streams if st.get("codec_type") == "video"), {})
    audio = next((st for st in streams if st.get("codec_type") == "audio"), {})
    def _int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    def _codec(value):
        name = str(value or "").lower()
        return name if re.fullmatch(r"[a-z0-9_]{1,64}", name) else ""
    video_codec = _codec(video.get("codec_name"))
    audio_codec = _codec(audio.get("codec_name"))
    parts = []
    if video_codec:
        size = f" {_int(video.get('width'))}x{_int(video.get('height'))}" if _int(video.get('width')) and _int(video.get('height')) else ""
        parts.append(f"vídeo={video_codec}{size}")
    if audio_codec:
        hz = _int(audio.get("sample_rate"))
        parts.append(f"áudio={audio_codec}" + (f" {hz} Hz" if hz else ""))
    return MediaProbeResult(
        ok=bool(video_codec or audio_codec),
        video_codec=video_codec,
        video_width=_int(video.get("width")),
        video_height=_int(video.get("height")),
        audio_codec=audio_codec,
        audio_sample_rate=_int(audio.get("sample_rate")),
        audio_channels=_int(audio.get("channels")),
        detail=" • ".join(parts) or "nenhuma faixa reconhecida",
        video_present=bool(video), audio_present=bool(audio),
        error_code="" if video or audio else "stream_not_found",
    )


def audio_gain_for_slider(value: int) -> float:
    """Map the 0..100 UI slider to useful listening gain.

    CCTV microphone tracks are frequently recorded at conservative levels.
    The old implementation mapped 75 to 0.75x and 100 to 1.0x, so the control
    could only attenuate. 0.2.24 makes 75 the unity point and reserves the top
    quarter for moderate amplification up to 2.0x (+6 dB).
    """
    value = max(0, min(int(value), 100))
    if value <= 0:
        return 0.0
    if value <= 75:
        return value / 75.0
    return 1.0 + ((value - 75) / 25.0)


def audio_filter_for_slider(value: int) -> str:
    return f"volume={audio_gain_for_slider(value):.3f}"


def _pulse_sink_inputs_for_pid(pid: int) -> list[int]:
    """Return Pulse/PipeWire sink-input IDs owned by *pid*.

    Fedora KDE normally exposes PipeWire through the PulseAudio compatibility
    API.  ``pactl -f json`` gives us a stable machine-readable way to find the
    sink input for ffplay/FFmpeg so the UI can change the listening volume
    without killing and reopening the RTSP session.
    """
    pactl = shutil.which("pactl")
    if not pactl or int(pid or 0) <= 0:
        return []
    try:
        cp = subprocess.run(
            [pactl, "-f", "json", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=0.8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if cp.returncode != 0:
        return []
    try:
        payload = json.loads(cp.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    wanted = str(int(pid))
    out: list[int] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        props = row.get("properties") or {}
        if not isinstance(props, dict):
            props = {}
        process_id = str(props.get("application.process.id") or props.get("application.process.binary") or "")
        # The binary fallback is intentionally not matched by value; only a real
        # process id is precise enough to avoid changing another application's
        # volume.
        if process_id != wanted:
            continue
        try:
            out.append(int(row.get("index")))
        except (TypeError, ValueError):
            continue
    return out


def set_process_audio_gain(pid: int, slider_value: int, *, retries: int = 1, retry_delay: float = 0.08) -> tuple[bool, str]:
    """Apply per-process listening gain through Pulse/PipeWire, without restart.

    ``75`` remains unity and ``100`` remains 2x.  Pulse/PipeWire accepts volume
    percentages above 100%, so the existing CCTV gain scale can be kept while
    avoiding the stop/reconnect behaviour of the old FFmpeg filter restart.
    """
    pactl = shutil.which("pactl")
    if not pactl:
        return False, "pactl ausente; volume dinâmico indisponível"
    gain = audio_gain_for_slider(slider_value)
    percent = max(0.0, min(gain * 100.0, 200.0))
    attempts = max(1, int(retries or 1))
    last = "sink de áudio ainda não apareceu"
    for attempt in range(attempts):
        ids = _pulse_sink_inputs_for_pid(pid)
        if ids:
            success = 0
            for sink_id in ids:
                try:
                    cp = subprocess.run(
                        [pactl, "set-sink-input-volume", str(sink_id), f"{percent:.0f}%"],
                        capture_output=True, text=True, timeout=0.8, check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    last = f"pactl: {type(exc).__name__}"
                    continue
                if cp.returncode == 0:
                    success += 1
                else:
                    last = sanitize_text((cp.stderr or cp.stdout or "").strip()) or f"pactl retornou {cp.returncode}"
            if success:
                return True, f"ganho local {percent:.0f}%"
        if attempt + 1 < attempts:
            time.sleep(max(0.01, float(retry_delay)))
    return False, last


def ordered_audio_urls(main_url: str = "", sub_url: str = "", rtsp_url: str = "", active: str = "sub") -> list[str]:
    """Return unique audio candidates, preferring the profile visible in Live View.

    Some cameras expose audio only on Main while video is normally shown from
    Substream in a mosaic (observed on several consumer/OEM cameras).  Audio
    therefore must not assume that the active video URL is also the only audio
    source.
    """
    main_url = str(main_url or "")
    sub_url = str(sub_url or "")
    rtsp_url = str(rtsp_url or "")
    first = main_url if str(active or "").lower() == "main" else sub_url
    second = sub_url if str(active or "").lower() == "main" else main_url
    result: list[str] = []
    for url in (first, second, rtsp_url):
        if url and url not in result:
            result.append(url)
    return result


class LiveAudioSession:
    """Play one RTSP audio track locally without touching the video decoder.

    ffplay is preferred because it integrates with the desktop audio stack and
    stays display-less with -nodisp.  A PulseAudio/PipeWire-compatible FFmpeg
    output is used as a fallback.  The caller is expected to enforce a single
    active audio source per monitoring workspace.
    """

    def __init__(
        self,
        url: str | list[str] | tuple[str, ...],
        username: str = "",
        password: str = "",
        volume: int = 75,
        *,
        audio_confirmed: bool = False,
        audio_codec: str = "",
        audio_sample_rate: int = 0,
        playback: bool = False,
        playback_speed: float = 1.0,
    ):
        if isinstance(url, (list, tuple)):
            self.urls = [str(item) for item in url if item]
        else:
            self.urls = [str(url)] if url else []
        self.url = self.urls[0] if self.urls else ""
        self.username = username
        self.password = password
        self.volume = max(0, min(int(volume), 100))
        self.audio_confirmed = bool(audio_confirmed)
        self.audio_codec = str(audio_codec or "").strip().lower()
        self.audio_sample_rate = int(audio_sample_rate or 0)
        self.playback = bool(playback)
        self.playback_speed = float(playback_speed) if playback else 1.0
        if self.playback_speed not in (0.5, 1.0, 2.0, 4.0, 8.0, 16.0):
            raise ValueError("Velocidade de áudio inválida")
        self.status: queue.Queue[str] = queue.Queue(maxsize=8)
        self.diagnostics: queue.Queue[str] = queue.Queue(maxsize=24)
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._volume_lock = threading.Lock()
        self._pending_volume: int | None = None
        self._volume_thread: threading.Thread | None = None
        self.dynamic_volume_active = False
        self.detected_codec = self.audio_codec
        self.detected_sample_rate = self.audio_sample_rate
        self.detected_url = ""
        self.current_state = "idle"
        self.current_backend = ""
        self.current_detail = ""
        self.had_transient_failure = False
        self._volume_attach_thread: threading.Thread | None = None

    def _set_state(self, state: str, detail: str = "", backend: str = "") -> None:
        self.current_state = str(state or "idle")
        self.current_detail = sanitize_text(detail)
        if backend:
            self.current_backend = str(backend)

    def current_state_text(self) -> str:
        if self.current_state == "active":
            codec = (self.detected_codec or self.audio_codec or "áudio").upper()
            hz = f" {int(self.detected_sample_rate or self.audio_sample_rate)} Hz" if int(self.detected_sample_rate or self.audio_sample_rate or 0) else ""
            backend = f" • {self.current_backend}" if self.current_backend else ""
            volume = " • volume dinâmico ativo" if self.dynamic_volume_active else ""
            return f"ATIVO • {codec}{hz}{backend}{volume}"
        if self.current_state == "opening":
            return "ABRINDO" + (f" • {self.current_detail}" if self.current_detail else "")
        if self.current_state == "retrying":
            return "RECUPERANDO" + (f" • {self.current_detail}" if self.current_detail else "")
        if self.current_state == "error":
            return "FALHA" + (f" • {self.current_detail}" if self.current_detail else "")
        if self.current_state == "stopped":
            return "DESLIGADO"
        return "AGUARDANDO"

    @property
    def player_available(self) -> bool:
        if shutil.which("ffplay"):
            return True
        outputs = ffmpeg_audio_output_devices()
        return bool(shutil.which("ffmpeg") and ({"pulse", "alsa"} & set(outputs)))

    def _push(self, q: queue.Queue[str], value: str) -> None:
        value = sanitize_text(value)
        if not value:
            return
        while True:
            try:
                q.put_nowait(value)
                return
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    return

    def _commands(self, url: str, transport: str = "tcp") -> list[tuple[str, list[str]]]:
        """Return local audio backends in the order most useful on Linux/PipeWire.

        0.2.32 promotes FFmpeg/Pulse-PipeWire to the first choice on Fedora/KDE.
        ffplay remains a compatibility fallback, but is no longer allowed to add
        startup latency when SDL is present yet unusable.
        """
        auth_url = authenticated_rtsp_url(url, self.username, self.password)
        commands: list[tuple[str, list[str]]] = []
        filter_value = "volume=1.000" if shutil.which("pactl") else audio_filter_for_slider(self.volume)
        if self.playback and self.playback_speed != 1.0:
            stages = (["atempo=0.5"] if self.playback_speed == 0.5
                      else ["atempo=2"] * (int(self.playback_speed).bit_length() - 1))
            filter_value = ",".join((*stages, filter_value))
        readrate = ["-readrate", f"{self.playback_speed:g}"] if self.playback else []
        ffmpeg = shutil.which("ffmpeg")
        outputs = ffmpeg_audio_output_devices() if ffmpeg else frozenset()
        if ffmpeg and "pulse" in outputs:
            commands.append(("FFmpeg/Pulse-PipeWire", [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning",
                "-rtsp_transport", transport, *list(ffmpeg_rtsp_timeout_args()),
                *readrate,
                "-i", auth_url, "-map", "0:a:0", "-vn", "-sn", "-dn",
                "-af", filter_value,
                "-acodec", "pcm_s16le", "-f", "pulse", "default",
            ]))
        if ffmpeg and "alsa" in outputs:
            commands.append(("FFmpeg/ALSA", [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning",
                "-rtsp_transport", transport, *list(ffmpeg_rtsp_timeout_args()),
                *readrate,
                "-i", auth_url, "-map", "0:a:0", "-vn", "-sn", "-dn",
                "-af", filter_value,
                "-acodec", "pcm_s16le", "-f", "alsa", "default",
            ]))
        ffplay = shutil.which("ffplay")
        if ffplay:
            commands.append(("ffplay/SDL", [
                ffplay, "-hide_banner", "-loglevel", "warning",
                "-nodisp", "-autoexit", "-vn", "-sn",
                "-rtsp_transport", transport,
                *list(ffmpeg_rtsp_timeout_args()),
                "-fflags", "nobuffer",
                "-analyzeduration", "250000",
                "-probesize", "65536",
                "-af", filter_value,
                "-volume", "100", auth_url,
            ]))
        return commands

    def _try_player(
        self,
        candidate: str,
        transport: str,
        *,
        codec: str = "áudio",
        sample_rate: int = 0,
        startup_grace: float = 0.45,
    ) -> tuple[bool, str]:
        commands = self._commands(candidate, transport)
        if not commands:
            return False, "nenhuma saída de áudio local compatível (ffplay/Pulse/ALSA)"
        hz = f" {sample_rate} Hz" if sample_rate else ""
        last_error = ""
        for backend, command in commands:
            if self._stop.is_set():
                return False, "interrompido"
            self._push(self.diagnostics, f"áudio: tentando saída {backend}")
            self._set_state("opening", f"{backend}", backend)
            try:
                proc = subprocess.Popen(
                    command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL, env=os.environ.copy(), close_fds=True,
                )
                self._process = proc
                deadline = time.monotonic() + max(0.20, float(startup_grace))
                while time.monotonic() < deadline and proc.poll() is None and not self._stop.is_set():
                    time.sleep(0.04)
                if self._stop.is_set():
                    return False, "interrompido"
                if proc.poll() is not None:
                    err = ""
                    if proc.stderr is not None:
                        try:
                            err = proc.stderr.read().decode("utf-8", "replace").strip()
                        except Exception:
                            err = ""
                    if err:
                        for line in err.splitlines()[-6:]:
                            if not _low_value_ffmpeg_warning(line):
                                self._push(self.diagnostics, f"áudio/{backend}: {line}")
                        last_error = sanitize_text(err.splitlines()[-1])
                        if _transient_rtsp_error(err):
                            self.had_transient_failure = True
                            self._set_state("retrying", "RTSP ocupado/503 transitório", backend)
                            self._process = None
                            return False, last_error
                    else:
                        last_error = f"{backend} encerrou com código {proc.returncode}"
                    self._process = None
                    continue

                self.detected_codec = str(codec or "").lower() if codec != "áudio" else self.detected_codec
                self.detected_sample_rate = int(sample_rate or self.detected_sample_rate or 0)
                self.detected_url = candidate
                self._set_state("active", "", backend)
                if self.had_transient_failure:
                    self._push(self.diagnostics, "✓ Áudio recuperado após falha transitória de abertura")
                if shutil.which("pactl"):
                    self._attach_dynamic_volume_async(proc.pid)
                self._push(self.status, f"🔊 Áudio ativo • {codec.upper()}{hz} • {backend}")
                if proc.stderr is not None:
                    for raw in iter(proc.stderr.readline, b""):
                        if self._stop.is_set():
                            break
                        line = raw.decode("utf-8", "replace").strip()
                        if line and not _low_value_ffmpeg_warning(line):
                            self._push(self.diagnostics, f"áudio/{backend}: {line}")
                rc = proc.wait() if proc.poll() is None else proc.returncode
                if self._stop.is_set():
                    return True, ""
                if rc in (0, None):
                    return True, ""
                last_error = f"{backend} encerrou com código {rc}"
                self._set_state("error", last_error, backend)
            except (OSError, ValueError) as exc:
                last_error = f"{backend}: {type(exc).__name__}: {exc}"
                self._set_state("error", last_error, backend)
                self._push(self.diagnostics, f"áudio: {last_error}")
            finally:
                self._process = None
        return False, last_error

    def _attach_dynamic_volume_async(self, pid: int) -> None:
        """Wait for the PipeWire sink-input without delaying RTSP audio startup."""
        if not shutil.which("pactl") or int(pid or 0) <= 0:
            return
        current = self._volume_attach_thread
        if current is not None and current.is_alive():
            return

        def worker() -> None:
            ok, detail = set_process_audio_gain(pid, self.volume, retries=18, retry_delay=0.12)
            if self._stop.is_set():
                return
            if ok:
                self.dynamic_volume_active = True
                self._push(self.diagnostics, "✓ controle de volume ativo • " + detail)
            else:
                self.dynamic_volume_active = False
                self._push(self.diagnostics, "áudio/volume: áudio ativo; controle dinâmico ainda não localizado")

        self._volume_attach_thread = threading.Thread(
            target=worker, name="sentinel-audio-volume-attach", daemon=True
        )
        self._volume_attach_thread.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._finished.clear()
        self._set_state("opening", "preparando áudio")
        self._thread = threading.Thread(target=self._run_wrapper, name="sentinel-audio", daemon=True)
        self._thread.start()

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def _run_wrapper(self) -> None:
        try:
            self._run()
        finally:
            self._finished.set()

    def stop(self) -> None:
        """Request audio stop without blocking the UI/event-loop caller."""
        self._stop.set()
        self._set_state("stopped")
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                return

            def reap() -> None:
                try:
                    proc.wait(timeout=0.7)
                except Exception:
                    try:
                        proc.kill()
                    except OSError:
                        pass

            threading.Thread(target=reap, name="sentinel-audio-reaper", daemon=True).start()
        # Do not wait/join here. The playback worker owns final cleanup and will
        # observe _stop after the process exits. This keeps clicks, tile changes
        # and Listen↔MIC transitions responsive.

    def _volume_worker_loop(self) -> None:
        while not self._stop.is_set():
            with self._volume_lock:
                value = self._pending_volume
                self._pending_volume = None
            if value is None:
                return
            proc = self._process
            if proc is None or proc.poll() is not None:
                return
            ok, detail = set_process_audio_gain(proc.pid, value, retries=2, retry_delay=0.05)
            self.dynamic_volume_active = bool(ok)
            self._push(self.diagnostics, ("✓ controle de volume ativo • " if ok else "áudio/volume: ") + detail)
            # Coalesce slider events: if a newer value arrived while pactl was
            # running, loop once more and apply only the newest one.
            time.sleep(0.02)

    def set_volume(self, volume: int) -> bool:
        """Change listening volume without stopping/reopening the RTSP player."""
        self.volume = max(0, min(int(volume), 100))
        proc = self._process
        if proc is None or proc.poll() is not None:
            return False
        if not shutil.which("pactl"):
            self._push(self.diagnostics, "áudio/volume: pactl ausente; alteração valerá na próxima abertura")
            return False
        with self._volume_lock:
            self._pending_volume = self.volume
            worker = self._volume_thread
            if worker is not None and worker.is_alive():
                return True
            self._volume_thread = threading.Thread(target=self._volume_worker_loop, name="sentinel-audio-volume", daemon=True)
            self._volume_thread.start()
        return True

    def restart_with_volume(self, volume: int) -> None:
        # Backward-compatible method name used by older callers/tests. 0.2.25
        # deliberately no longer restarts the player.
        self.set_volume(volume)

    def latest_status(self) -> str | None:
        latest = None
        while True:
            try:
                latest = self.status.get_nowait()
            except queue.Empty:
                return latest

    def drain_diagnostics(self) -> list[str]:
        items = []
        while True:
            try:
                items.append(self.diagnostics.get_nowait())
            except queue.Empty:
                return items

    def _run(self) -> None:
        if not self.player_available:
            self._push(self.status, "Áudio indisponível • player local ausente")
            return
        if not self.urls:
            self._push(self.status, "Áudio indisponível • nenhuma URL de mídia")
            return

        if self.playback:
            probe = probe_rtsp_media_capabilities(
                self.url, self.username, self.password, transport="tcp", timeout=4.0)
            if self._stop.is_set():
                return
            if not probe.has_audio:
                self._push(self.status, "Gravação sem faixa de áudio" if probe.has_video else
                           "Áudio não confirmado nesta gravação")
                return
            ok, detail = self._try_player(self.url, "tcp", codec=probe.audio_codec or "áudio",
                                          sample_rate=probe.audio_sample_rate or 0)
            if not self._stop.is_set():
                self._push(self.status, "Fim do áudio gravado" if ok else
                           "Não foi possível reproduzir o áudio gravado")
                if detail:
                    self._push(self.diagnostics, detail)
            return

        # Fast path: channel metadata already carries a confirmed audio track.
        # Avoid running a full ffprobe (which can take several seconds on RTSP)
        # before every click. If direct playback fails, fall back to the complete
        # Main/Sub + TCP/UDP probing path below.
        if self.audio_confirmed:
            codec = self.audio_codec or "áudio"
            if codec and codec != "áudio" and not local_decoder_available(codec):
                self._push(self.diagnostics, f"áudio: decoder local ausente para {codec}; executando diagnóstico completo")
            else:
                self._push(self.status, "Áudio: abrindo faixa confirmada…")
                for url_index, candidate in enumerate(self.urls, start=1):
                    if self._stop.is_set():
                        return
                    for attempt, delay in enumerate((0.0, 0.8, 1.6), start=1):
                        if delay and self._stop.wait(delay):
                            return
                        self._push(
                            self.diagnostics,
                            f"áudio rápido: perfil {url_index}/{len(self.urls)} via TCP"
                            + (f" • retry {attempt}/3" if attempt > 1 else ""),
                        )
                        ok, err = self._try_player(
                            candidate, "tcp", codec=codec, sample_rate=self.audio_sample_rate, startup_grace=0.45
                        )
                        if ok or self._stop.is_set():
                            return
                        if err:
                            self._push(self.diagnostics, f"áudio rápido: {err}")
                        if not _transient_rtsp_error(err):
                            break
                        self._set_state("retrying", f"503 transitório • tentativa {attempt + 1}/3")
                        if attempt < 3:
                            self._push(self.status, f"Áudio ocupado no DVR • nova tentativa em {int((0.8, 1.6)[attempt - 1] * 10) / 10:g} s")

        self._push(self.status, "Áudio: procurando faixa no Main/Sub…")
        saw_track = False
        last_error = ""
        for url_index, candidate in enumerate(self.urls, start=1):
            if self._stop.is_set():
                return
            for transport in ("tcp", "udp"):
                if self._stop.is_set():
                    return
                probe = probe_rtsp_media_capabilities(
                    candidate, self.username, self.password, transport=transport, timeout=4.0
                )
                self._push(
                    self.diagnostics,
                    f"áudio: perfil {url_index}/{len(self.urls)} via {transport.upper()} • {probe.detail}",
                )
                if not probe.has_audio:
                    last_error = probe.detail or "sem faixa de áudio"
                    continue
                saw_track = True
                codec = probe.audio_codec or "áudio"
                if codec and not local_decoder_available(codec):
                    last_error = f"decoder local ausente para {codec}"
                    self._push(self.diagnostics, f"áudio: {last_error}")
                    continue

                self.detected_codec = codec
                self.detected_sample_rate = int(probe.audio_sample_rate or 0)
                self.detected_url = candidate
                hz = f" {probe.audio_sample_rate} Hz" if probe.audio_sample_rate else ""
                self._push(self.status, f"Áudio confirmado • {codec.upper()}{hz} • selecionando saída local…")
                ok, last_error = self._try_player(
                    candidate, transport, codec=codec, sample_rate=probe.audio_sample_rate, startup_grace=0.55
                )
                if ok or self._stop.is_set():
                    return

        if self._stop.is_set():
            return
        if saw_track:
            detail = "Falha na saída de áudio local" + (f" • {last_error}" if last_error else "")
            self._set_state("error", detail)
            self._push(self.status, detail)
        else:
            detail = "Sem faixa de áudio nos streams Main/Sub" + (f" • {last_error}" if last_error else "")
            self._set_state("error", detail)
            self._push(self.status, detail)

@dataclass(slots=True)
class FramePacket:
    pixels: bytes
    width: int = FRAME_WIDTH
    height: int = FRAME_HEIGHT


class LiveStreamSession:
    """Read-only FFmpeg RTSP decoder isolated from the Qt GUI thread.

    Supports an optional fallback profile. In automatic mode this allows the
    mosaic to try substream first and transparently fall back to main stream.
    Frames, status, and sanitized diagnostics are exchanged through bounded
    queues so no Qt object is touched from worker threads.
    """

    def __init__(
        self,
        url: str,
        username: str = "",
        password: str = "",
        fps: int = 10,
        *,
        profile_name: str = "stream",
        fallback_url: str = "",
        fallback_name: str = "",
        stop_after_initial_failures: int = 0,
        transport_fallback: bool = False,
        playback: bool = False,
        playback_speed: float = 1.0,
    ):
        self.url = url
        self.username = username
        self.password = password
        self.fps = max(1, min(int(fps), 20))
        self.profile_name = profile_name or "stream"
        self.fallback_url = fallback_url
        self.fallback_name = fallback_name or "fallback"
        self.stop_after_initial_failures = max(0, int(stop_after_initial_failures or 0))
        self.transport_fallback = bool(transport_fallback)
        self.playback = bool(playback)
        self.playback_speed = float(playback_speed) if playback else 1.0
        if self.playback_speed not in (0.5, 1.0, 2.0, 4.0, 8.0, 16.0):
            raise ValueError("Velocidade de reprodução inválida")
        self.frames: queue.Queue[FramePacket] = queue.Queue(maxsize=2)
        self.status: queue.Queue[str] = queue.Queue(maxsize=8)
        self.diagnostics: queue.Queue[str] = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self.active_profile = self.profile_name
        self.attempts = 0
        self.reconnects = 0
        self.ever_had_frame = False
        self._fatal_decoder_error = threading.Event()
        self._network_failure = threading.Event()
        self._network_failure_detail = ""

    @property
    def decoder_available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def _try_player(
        self,
        candidate: str,
        transport: str,
        *,
        codec: str = "áudio",
        sample_rate: int = 0,
        startup_grace: float = 0.45,
    ) -> tuple[bool, str]:
        commands = self._commands(candidate, transport)
        if not commands:
            return False, "nenhuma saída de áudio local compatível (ffplay/Pulse/ALSA)"
        hz = f" {sample_rate} Hz" if sample_rate else ""
        last_error = ""
        for backend, command in commands:
            if self._stop.is_set():
                return False, "interrompido"
            self._push(self.diagnostics, f"áudio: tentando saída {backend}")
            try:
                proc = subprocess.Popen(
                    command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL, env=os.environ.copy(), close_fds=True,
                )
                self._process = proc
                deadline = time.monotonic() + max(0.20, float(startup_grace))
                while time.monotonic() < deadline and proc.poll() is None and not self._stop.is_set():
                    time.sleep(0.04)
                if self._stop.is_set():
                    return False, "interrompido"
                if proc.poll() is not None:
                    err = ""
                    if proc.stderr is not None:
                        try:
                            err = proc.stderr.read().decode("utf-8", "replace").strip()
                        except Exception:
                            err = ""
                    if err:
                        for line in err.splitlines()[-6:]:
                            self._push(self.diagnostics, f"áudio/{backend}: {line}")
                        last_error = sanitize_text(err.splitlines()[-1])
                    else:
                        last_error = f"{backend} encerrou com código {proc.returncode}"
                    self._process = None
                    continue

                self._push(self.status, f"🔊 Áudio ativo • {codec.upper()}{hz} • {backend}")
                if proc.stderr is not None:
                    for raw in iter(proc.stderr.readline, b""):
                        if self._stop.is_set():
                            break
                        line = raw.decode("utf-8", "replace").strip()
                        if line:
                            self._push(self.diagnostics, f"áudio/{backend}: {line}")
                rc = proc.wait() if proc.poll() is None else proc.returncode
                if self._stop.is_set():
                    return True, ""
                if rc in (0, None):
                    return True, ""
                last_error = f"{backend} encerrou com código {rc}"
            except (OSError, ValueError) as exc:
                last_error = f"{backend}: {type(exc).__name__}: {exc}"
                self._push(self.diagnostics, f"áudio: {last_error}")
            finally:
                self._process = None
        return False, last_error

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sentinel-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        thread = self._thread
        # Never let a decoder shutdown stall the Qt thread for ~1.5 s. RTSP
        # readers can be blocked in pipe I/O even after terminate(); give them a
        # short grace period, then kill and return control to the interface.
        if thread and thread.is_alive():
            thread.join(timeout=0.30)
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        if thread and thread.is_alive():
            thread.join(timeout=0.15)
        self._process = None

    def latest_frame(self) -> FramePacket | None:
        latest = None
        while True:
            try:
                latest = self.frames.get_nowait()
            except queue.Empty:
                break
        return latest

    def latest_status(self) -> str | None:
        latest = None
        while True:
            try:
                latest = self.status.get_nowait()
            except queue.Empty:
                break
        return latest

    def drain_diagnostics(self) -> list[str]:
        items = []
        while True:
            try:
                items.append(self.diagnostics.get_nowait())
            except queue.Empty:
                break
        return items

    def _push_status(self, text: str) -> None:
        while True:
            try:
                self.status.put_nowait(text)
                return
            except queue.Full:
                try:
                    self.status.get_nowait()
                except queue.Empty:
                    return

    def _push_diag(self, text: str) -> None:
        text = sanitize_text(text)
        if not text:
            return
        stamp = time.strftime("%H:%M:%S")
        entry = f"[{stamp}] {text}"
        while True:
            try:
                self.diagnostics.put_nowait(entry)
                return
            except queue.Full:
                try:
                    self.diagnostics.get_nowait()
                except queue.Empty:
                    return

    def _push_frame(self, frame: FramePacket) -> None:
        while True:
            try:
                self.frames.put_nowait(frame)
                return
            except queue.Full:
                try:
                    self.frames.get_nowait()
                except queue.Empty:
                    return

    def _command(self, url: str, transport: str = "tcp") -> list[str]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg não encontrado")
        auth_url = authenticated_rtsp_url(url, self.username, self.password)
        vf = (
            (f"setpts=PTS/{self.playback_speed:g}," if self.playback else "") +
            f"scale={FRAME_WIDTH}:{FRAME_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={FRAME_WIDTH}:{FRAME_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={self.fps}"
        )
        timeout_args = list(ffmpeg_rtsp_timeout_args())
        return [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel", "warning",
            "-rtsp_transport", transport,
            *timeout_args,
            *(["-readrate", f"{self.playback_speed:g}"] if self.playback else []),
            "-i", auth_url,
            "-map", "0:v:0",
            "-an", "-sn", "-dn",
            "-vf", vf,
            "-pix_fmt", "rgb24",
            "-f", "rawvideo",
            "pipe:1",
        ]

    @staticmethod
    def _read_exact(stream, size: int, stop_event: threading.Event) -> bytes:
        buf = bytearray()
        while len(buf) < size and not stop_event.is_set():
            chunk = stream.read(size - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def _stderr_reader(self, stream, profile: str) -> None:
        try:
            for raw in iter(stream.readline, b""):
                if self._stop.is_set():
                    break
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    lowered = line.lower()
                    network_reason = _network_failure_reason(line)
                    if network_reason:
                        if not self._network_failure.is_set():
                            self._network_failure_detail = network_reason
                            self._push_diag(f"{profile}: conectividade • {network_reason}; troca de stream/transporte será ignorada")
                        self._network_failure.set()
                    elif self._network_failure.is_set() and (
                        "error opening input" in lowered or "failed to open" in lowered
                    ):
                        # Consequence of the already-classified routing failure.
                        pass
                    elif not _low_value_ffmpeg_warning(line):
                        self._push_diag(f"{profile}: {line}")
                    if ("option " in lowered and "not found" in lowered) or "unrecognized option" in lowered:
                        self._fatal_decoder_error.set()
                    if "no decoder found for:" in lowered:
                        codec = line.rsplit(":", 1)[-1].strip().upper() or "codec"
                        self._push_status(f"Decoder {codec} indisponível • veja Diagnóstico")
                        self._fatal_decoder_error.set()
        except Exception as exc:
            self._push_diag(f"leitor de diagnóstico: {type(exc).__name__}: {exc}")

    def _attempt_profile(self, url: str, profile: str, transport: str = "tcp") -> bool:
        self._network_failure.clear()
        self._network_failure_detail = ""
        self.attempts += 1
        self.active_profile = profile
        transport_label = transport.upper()
        self._push_status(f"Conectando • {profile} • {transport_label}")
        self._push_diag(f"Tentativa {self.attempts}: iniciando {profile} via {transport_label}")
        got_frame = False
        try:
            proc = subprocess.Popen(
                self._command(url, transport),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                bufsize=0,
                close_fds=True,
                env=os.environ.copy(),
            )
            self._process = proc
            assert proc.stdout is not None
            if proc.stderr is not None:
                threading.Thread(
                    target=self._stderr_reader,
                    args=(proc.stderr, profile),
                    name="sentinel-live-stderr",
                    daemon=True,
                ).start()
            while not self._stop.is_set():
                raw = self._read_exact(proc.stdout, FRAME_SIZE, self._stop)
                if len(raw) != FRAME_SIZE:
                    break
                if not got_frame:
                    got_frame = True
                    self.ever_had_frame = True
                    self._push_status(f"● AO VIVO • {profile} • {transport_label}")
                    self._push_diag(f"{profile}: primeiro frame recebido via {transport_label}")
                self._push_frame(FramePacket(raw))
        except (OSError, ValueError) as exc:
            self._push_diag(f"{profile}: falha ao iniciar decoder: {type(exc).__name__}: {exc}")
        finally:
            proc = self._process
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except Exception:
                    try:
                        proc.kill()
                    except OSError:
                        pass
            self._process = None
        if not got_frame:
            self._push_diag(f"{profile}: nenhum frame recebido")
        return got_frame

    def _run(self) -> None:
        if not self.decoder_available:
            self._push_status("FFmpeg não encontrado")
            self._push_diag("FFmpeg não encontrado no PATH")
            return

        consecutive_failures = 0
        network_failures = 0
        while not self._stop.is_set():
            self._fatal_decoder_error.clear()
            got = self._attempt_profile(self.url, self.profile_name, "tcp")
            network_problem = bool((not got) and self._network_failure.is_set())

            # Socket/routing failures affect every stream on the same host. Do
            # not waste time cycling TCP/UDP or Main/Sub in that condition.
            if not got and not network_problem and self.transport_fallback and not self._stop.is_set() and not self._fatal_decoder_error.is_set():
                self._push_status(f"Transporte TCP sem vídeo • tentando UDP")
                self._push_diag(f"{self.profile_name}: TCP não entregou frames; tentando UDP antes de trocar o perfil")
                got = self._attempt_profile(self.url, self.profile_name, "udp")
                network_problem = bool((not got) and self._network_failure.is_set())
            if self._stop.is_set():
                break
            if self._fatal_decoder_error.is_set():
                self._push_status("FFmpeg incompatível • veja Diagnóstico")
                self._push_diag("Live View interrompido: o FFmpeg rejeitou uma opção de linha de comando; evitando tentativas em loop.")
                break

            if not got and not network_problem and self.fallback_url:
                self._push_status(f"Fallback → {self.fallback_name}")
                self._push_diag(f"{self.profile_name} falhou; tentando fallback {self.fallback_name}")
                got = self._attempt_profile(self.fallback_url, self.fallback_name, "tcp")
                network_problem = bool((not got) and self._network_failure.is_set())
                if not got and not network_problem and self.transport_fallback and not self._stop.is_set() and not self._fatal_decoder_error.is_set():
                    self._push_diag(f"{self.fallback_name}: TCP não entregou frames; tentando UDP")
                    got = self._attempt_profile(self.fallback_url, self.fallback_name, "udp")
                    network_problem = bool((not got) and self._network_failure.is_set())
                if self._stop.is_set():
                    break
                if self._fatal_decoder_error.is_set():
                    self._push_status("FFmpeg incompatível • veja Diagnóstico")
                    self._push_diag("Live View interrompido: o FFmpeg rejeitou uma opção de linha de comando; evitando tentativas em loop.")
                    break

            if network_problem:
                network_failures += 1
                consecutive_failures = 0
                schedule = (3.0, 8.0, 15.0, 30.0)
                delay = schedule[min(network_failures - 1, len(schedule) - 1)]
                reason = self._network_failure_detail or "host/rede inacessível"
                self._push_status(f"Host temporariamente inacessível • nova tentativa em {int(delay)} s")
                self._push_diag(
                    f"Conectividade: {reason}; ciclo RTSP abreviado. Nova tentativa em {int(delay)} s com o perfil principal."
                )
                self._stop.wait(delay)
                continue

            network_failures = 0
            if got:
                if self.playback:
                    self._push_status("Fim do trecho • selecione outro trecho para continuar")
                    break
                consecutive_failures = 0
                self.reconnects += 1
                delay = 2.0
                self._push_status(f"Reconectando em 2 s • {self.active_profile}")
            else:
                consecutive_failures += 1
                if (
                    self.stop_after_initial_failures
                    and not self.ever_had_frame
                    and consecutive_failures >= self.stop_after_initial_failures
                ):
                    self._push_status("Stream não validado • reconexão parada")
                    self._push_diag(
                        f"Nenhum frame após {consecutive_failures} ciclo(s); reconexão automática interrompida para evitar loop contínuo."
                    )
                    break
                if consecutive_failures <= 3:
                    delay = 2.0
                elif consecutive_failures <= 6:
                    delay = 5.0
                else:
                    delay = 10.0
                self._push_status(f"Sem vídeo • nova tentativa em {int(delay)} s")
            self._stop.wait(delay)


class DvripLiveStreamSession(LiveStreamSession):
    """Decode native XM/Sofia OPMonitor video through FFmpeg.

    Used only for validated ``dvrip://`` sources, primarily fixed lenses on
    multi-lens IT-Blue/XM cameras whose RTSP server exposes only the PTZ view.
    No device configuration is changed.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dvrip_session: DvripSession | None = None

    @staticmethod
    def _dvrip_target(url: str) -> tuple[str, int, int, int]:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "dvrip" or not parsed.hostname:
            raise ValueError("URL DVRIP inválida")
        query = parse_qs(parsed.query)
        try:
            channel = max(0, int((query.get("channel") or ["0"])[0]))
        except (TypeError, ValueError):
            channel = 0
        try:
            subtype = 1 if int((query.get("subtype") or ["0"])[0]) == 1 else 0
        except (TypeError, ValueError):
            subtype = 0
        return parsed.hostname, int(parsed.port or 34567), channel, subtype

    def _dvrip_decoder_command(self, codec: str) -> list[str]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg não encontrado")
        fmt = "hevc" if codec == "hevc" else "h264"
        vf = (
            f"scale={FRAME_WIDTH}:{FRAME_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={FRAME_WIDTH}:{FRAME_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={self.fps}"
        )
        return [
            ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-f", fmt, "-i", "pipe:0",
            "-map", "0:v:0", "-an", "-sn", "-dn",
            "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ]

    @staticmethod
    def _video_payload(ptype: int, packet: bytes) -> bytes:
        if ptype in (0xFC, 0xFE):
            return packet[16:]
        if ptype == 0xFD:
            return packet[8:]
        return b""

    def stop(self) -> None:
        self._stop.set()
        session = self._dvrip_session
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        super().stop()

    def _attempt_profile(self, url: str, profile: str, transport: str = "tcp") -> bool:
        self._network_failure.clear()
        self._network_failure_detail = ""
        self.attempts += 1
        self.active_profile = profile
        self._push_status(f"Conectando • {profile} • DVRIP")
        self._push_diag(f"Tentativa {self.attempts}: iniciando {profile} via DVRIP/34567")
        got_frame = False
        proc = None
        session = None
        feeder_done = threading.Event()
        feeder_error: list[str] = []
        try:
            host, port, channel, subtype = self._dvrip_target(url)
            session = DvripSession(host, self.username, self.password, port=port, timeout=3.0)
            self._dvrip_session = session
            session.connect(); session.login(); session.monitor_claim(channel, subtype); session.monitor_start(channel, subtype)

            codec = ""
            first_packet: tuple[int, bytes] | None = None
            # Wait for a keyframe because it carries the media codec marker.
            deadline = time.monotonic() + 6.0
            while not self._stop.is_set() and time.monotonic() < deadline:
                ptype, packet = session.read_media_packet()
                if ptype not in (0xFC, 0xFE):
                    continue
                media_code = int(packet[4]) if len(packet) > 5 else 0
                if media_code in (0x02, 0x12):
                    codec = "h264"
                elif media_code in (0x03, 0x13, 0x43, 0x53):
                    codec = "hevc"
                else:
                    raise DvripError(f"codec de vídeo DVRIP não suportado: 0x{media_code:02x}")
                first_packet = (ptype, packet)
                break
            if not first_packet or not codec:
                raise DvripError("DVRIP conectado, mas nenhum keyframe de vídeo foi recebido")

            proc = subprocess.Popen(
                self._dvrip_decoder_command(codec), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0, close_fds=True, env=os.environ.copy(),
            )
            self._process = proc
            assert proc.stdin is not None and proc.stdout is not None
            if proc.stderr is not None:
                threading.Thread(
                    target=self._stderr_reader, args=(proc.stderr, profile),
                    name="sentinel-dvrip-stderr", daemon=True,
                ).start()

            def feed() -> None:
                pending = [first_packet]
                try:
                    while not self._stop.is_set() and proc.poll() is None:
                        if pending:
                            ptype, packet = pending.pop(0)
                        else:
                            ptype, packet = session.read_media_packet()
                        payload = self._video_payload(ptype, packet)
                        if not payload:
                            continue
                        try:
                            proc.stdin.write(payload)
                        except (BrokenPipeError, OSError):
                            break
                except Exception as exc:
                    if not self._stop.is_set():
                        feeder_error.append(f"{type(exc).__name__}: {exc}")
                finally:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
                    feeder_done.set()

            threading.Thread(target=feed, name="sentinel-dvrip-feed", daemon=True).start()

            while not self._stop.is_set():
                raw = self._read_exact(proc.stdout, FRAME_SIZE, self._stop)
                if len(raw) != FRAME_SIZE:
                    if feeder_done.is_set():
                        break
                    if proc.poll() is not None:
                        break
                    continue
                if not got_frame:
                    got_frame = True
                    self.ever_had_frame = True
                    self._push_status(f"● AO VIVO • {profile} • DVRIP")
                    self._push_diag(f"{profile}: primeiro frame {codec.upper()} recebido por DVRIP canal {channel}")
                self._push_frame(FramePacket(raw))
            if feeder_error:
                self._push_diag(f"{profile}: feeder DVRIP encerrou: {feeder_error[-1]}")
        except (OSError, ValueError, DvripError) as exc:
            self._push_diag(f"{profile}: falha DVRIP: {type(exc).__name__}: {exc}")
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            self._dvrip_session = None
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate(); proc.wait(timeout=0.5)
                except Exception:
                    try:
                        proc.kill()
                    except OSError:
                        pass
            self._process = None
        if not got_frame:
            self._push_diag(f"{profile}: nenhum frame DVRIP recebido")
        return got_frame


def create_live_stream_session(
    url: str, username: str = "", password: str = "", fps: int = 10, **kwargs
) -> LiveStreamSession:
    """Create the proper read-only live decoder for RTSP or native DVRIP."""
    scheme = urlparse(str(url or "")).scheme.lower()
    cls = DvripLiveStreamSession if scheme == "dvrip" else LiveStreamSession
    return cls(url, username, password, fps=fps, **kwargs)

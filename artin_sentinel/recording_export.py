"""Convert a recorder playback stream into an atomic local MP4 export."""

from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading

from .live import authenticated_rtsp_url, ffmpeg_rtsp_timeout_args


class RecordingExportError(RuntimeError):
    pass


def export_mp4(url: str, username: str, password: str, destination: str,
               duration_seconds: int, *, cancel: threading.Event | None = None,
               progress=None, include_audio: bool = True) -> Path:
    """Save only a completed conversion; never overwrite an existing export."""
    ffmpeg = shutil.which("ffmpeg")
    target = Path(destination)
    if not ffmpeg or not 1 <= duration_seconds <= 86400 or target.suffix.lower() != ".mp4":
        raise RecordingExportError("Exportação inválida ou FFmpeg indisponível")
    if target.exists():
        raise RecordingExportError("O arquivo de destino já existe; escolha outro nome")
    if cancel is not None and cancel.is_set():
        raise RecordingExportError("Exportação cancelada")
    fd, tmp_name = tempfile.mkstemp(prefix=".sentinel-export-", suffix=".mp4", dir=target.parent)
    os.close(fd)
    proc = None
    try:
        command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-stats_period", "1",
                   "-progress", "pipe:1", "-rtsp_transport", "tcp", *ffmpeg_rtsp_timeout_args(),
                   "-i", authenticated_rtsp_url(url, username, password), "-t", str(duration_seconds),
                   "-map", "0:v:0",
                   *(["-map", "0:a?", "-c:a", "aac"] if include_audio else ["-an"]),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-movflags", "+faststart", "-f", "mp4", "-y", tmp_name]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, text=True, close_fds=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel is not None and cancel.is_set():
                proc.terminate()
                break
            if line.startswith("out_time=") and progress:
                try:
                    elapsed = (datetime.strptime(line.split("=", 1)[1].strip(), "%H:%M:%S.%f") -
                               datetime(1900, 1, 1)).total_seconds()
                    progress(f"Convertendo… {min(99, int(100 * elapsed / duration_seconds))}%")
                except ValueError:
                    pass
        try:
            code = proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            code = -1
        if cancel is not None and cancel.is_set():
            raise RecordingExportError("Exportação cancelada")
        if code != 0 or Path(tmp_name).stat().st_size < 1024:
            raise RecordingExportError("O gravador ou FFmpeg não entregou um MP4 completo")
        # Same-directory hard link publishes the complete MP4 atomically and
        # refuses to replace a file created while the conversion ran.
        os.link(tmp_name, target)
        if progress:
            progress("Convertido • 100%")
        return target
    except FileExistsError as exc:
        raise RecordingExportError("O arquivo de destino já existe; escolha outro nome") from exc
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        Path(tmp_name).unlink(missing_ok=True)

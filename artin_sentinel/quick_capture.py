"""Operator initiated live capture into a completed MP4 file."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading

from .live import authenticated_rtsp_url, ffmpeg_rtsp_timeout_args


class ManualRecording:
    def __init__(self, url: str, username: str, password: str, destination: str):
        self.destination = Path(destination)
        self.error = ""
        self.finished = False
        self.saved = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(url, username, password), daemon=True)

    def start(self):
        if self.destination.suffix.lower() != ".mp4" or self.destination.exists():
            raise ValueError("Escolha um novo arquivo MP4")
        if not shutil.which("ffmpeg") or not self.destination.parent.is_dir():
            raise ValueError("FFmpeg ou pasta de destino indisponível")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self, url, username, password):
        tmp_name = ""
        proc = None
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".sentinel-capture-", suffix=".mp4", dir=self.destination.parent)
            os.close(fd)
            cmd = [shutil.which("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-rtsp_transport", "tcp", *ffmpeg_rtsp_timeout_args(),
                   "-i", authenticated_rtsp_url(url, username, password),
                   "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "24", "-c:a", "aac", "-movflags", "+faststart", "-f", "mp4", "-y", tmp_name]
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
            while proc.poll() is None and not self._stop.wait(0.2):
                pass
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGINT)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            if Path(tmp_name).stat().st_size < 1024:
                raise RuntimeError("Nenhum vídeo foi recebido; arquivo não salvo")
            os.link(tmp_name, self.destination)
            self.saved = True
        except FileExistsError:
            self.error = "O arquivo já existe; gravação não substituída"
        except Exception as exc:
            self.error = str(exc).replace(password, "[oculto]") if password else str(exc)
        finally:
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)
            self.finished = True

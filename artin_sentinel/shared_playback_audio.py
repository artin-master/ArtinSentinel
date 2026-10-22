"""Optional recording audio consumes the video transport; it never opens a DVR session."""
import os
import queue
import select
import shutil
import subprocess
import threading
import time
from .intelbras_cloud_audio import IntelbrasCloudAudioSession
from .media_process import terminate_media_process


class PlaybackFanout:
    def __init__(self):
        self.lock = threading.Lock(); self.subscriber = None
        self.stop = threading.Event(); self.done = threading.Event(); self.ready = threading.Event()
        self.thread = None; self.audio_overruns = 0

    def subscribe(self):
        stream = queue.Queue(maxsize=64)  # At most 4 MiB, independently of video.
        with self.lock:
            if self.subscriber is not None:
                self._finish(self.subscriber)
            self.subscriber = stream
            if self.done.is_set(): self._finish(stream)
        return stream

    @staticmethod
    def _finish(stream):
        while True:
            try: stream.put_nowait(None); return
            except queue.Full:
                try: stream.get_nowait()
                except queue.Empty: pass

    def unsubscribe(self, stream):
        with self.lock:
            if self.subscriber is stream: self.subscriber = None
        self._finish(stream)

    def start(self, source, target):
        self.ready.set()
        def pump():
            try:
                os.set_blocking(source, False); os.set_blocking(target, False)
                while not self.stop.is_set():
                    if not select.select([source], [], [], .1)[0]: continue
                    data = os.read(source, 65536)
                    if not data: break
                    with self.lock:
                        if self.subscriber is not None:
                            try: self.subscriber.put_nowait(data)
                            except queue.Full:
                                self.audio_overruns += 1
                                self._finish(self.subscriber); self.subscriber = None
                    remaining = memoryview(data)
                    while remaining and not self.stop.is_set():
                        if not select.select([], [target], [], .1)[1]: continue
                        try: count = os.write(target, remaining)
                        except BlockingIOError: continue
                        remaining = remaining[count:]
            except OSError:
                pass
            finally:
                for fd in (source, target):
                    try: os.close(fd)
                    except OSError: pass
                self.done.set()
                with self.lock:
                    if self.subscriber is not None: self._finish(self.subscriber)
        self.thread = threading.Thread(target=pump, name='playback-media', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread is not None: self.thread.join(1)


class SharedPlaybackAudioSession(IntelbrasCloudAudioSession):
    def __init__(self, source, *, volume=100):
        self.source = source; self.fanout = source._playback_fanout
        self._initial_stream = self.fanout.subscribe()
        super().__init__(source.url, volume=volume, playback=True, playback_speed=source.playback_speed)

    def _route(self, url):
        return self.source._route(url)

    def _commands(self, *args):
        commands = super()._commands(*args)
        for _name, command in commands:
            if self.playback_speed != 1:
                stages = ['atempo=0.5'] if self.playback_speed == .5 else ['atempo=2'] * (int(self.playback_speed).bit_length()-1)
                index = command.index('-af')+1
                command[index] = ','.join(stages+[command[index]])
        return commands

    def stop(self):
        super().stop()
        self.fanout.unsubscribe(self._initial_stream)

    def _run(self):
        try:
            self._consume()
        finally:
            self.fanout.unsubscribe(self._initial_stream)

    def _consume(self):
        self._push(self.status, 'Áudio: aguardando a sessão de vídeo…')
        deadline = time.monotonic()+65
        while not self.fanout.ready.is_set():
            if (self._stop.is_set() or self.source._stop.is_set() or self.source._finished.is_set()
                    or time.monotonic()>deadline): return
            self._stop.wait(.1)
        for attempt, (backend, command) in enumerate(self._commands()):
            if self._stop.is_set() or self.fanout.done.is_set(): break
            self._push(self.diagnostics, 'Áudio gravado • tentando saída '+backend)
            overrun_before = self.fanout.audio_overruns
            stream = self._initial_stream if attempt == 0 else self.fanout.subscribe()
            proc = None; writer = None
            input_done = threading.Event()
            try:
                proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, close_fds=True)
                with self._process_lock: self._process = proc
                def feed():
                    try:
                        fd = proc.stdin.fileno(); os.set_blocking(fd, False)
                        while not self._stop.is_set() and not input_done.is_set():
                            try: data = stream.get(timeout=.1)
                            except queue.Empty: continue
                            if data is None: break
                            data = memoryview(data)
                            while data and not self._stop.is_set() and not input_done.is_set():
                                if not select.select([], [fd], [], .1)[1]: continue
                                try: size = os.write(fd, data)
                                except BlockingIOError: continue
                                data = data[size:]
                    except (OSError, ValueError): pass
                    finally:
                        input_done.set()
                        try: proc.stdin.close()
                        except (OSError, ValueError): pass
                writer = threading.Thread(target=feed, name='recording-audio', daemon=True); writer.start()
                deadline = time.monotonic()+15; buffer = bytearray(); confirmed = False
                while not self._stop.is_set() and proc.poll() is None:
                    if self.fanout.done.is_set() or input_done.is_set(): break
                    if not confirmed and time.monotonic() > deadline: break
                    if not select.select([proc.stderr], [], [], .1)[0]: continue
                    data = os.read(proc.stderr.fileno(), 8192)
                    if not data: break
                    buffer.extend(data)
                    while b'\n' in buffer:
                        line, _, rest = buffer.partition(b'\n'); buffer[:] = rest
                        if line.startswith((b'out_time_us=', b'out_time_ms=')):
                            try: positive = int(line.split(b'=', 1)[1]) > 0
                            except ValueError: positive = False
                            if positive and not confirmed:
                                confirmed = True; self._had_audio = True; self.detected_url = self.url
                                self.current_backend = backend; self._set_state('active', '', backend)
                                self._push(self.status, '🔊 Áudio da mesma sessão de gravação • '+backend)
                                if shutil.which('pactl'): self._attach_dynamic_volume_async(proc.pid)
                        elif b'=' not in line and line.strip():
                            self._push(self.diagnostics, line.decode('utf-8', 'replace')[:500])
                if not confirmed and not self._stop.is_set():
                    if self.fanout.audio_overruns > overrun_before:
                        reason = 'fila de áudio atingiu o limite; vídeo preservado'
                    elif proc.poll() is not None:
                        reason = 'processo de áudio encerrado • código '+str(proc.returncode)
                    elif time.monotonic() > deadline:
                        reason = 'sem áudio confirmado no prazo de 15 segundos'
                    else:
                        reason = 'entrada compartilhada de áudio encerrada'
                    self._push(self.diagnostics, backend+' • '+reason)
                if confirmed:
                    if not self._stop.is_set():
                        self._set_state('unavailable', 'Áudio interrompido; vídeo preservado')
                        self._push(self.status, 'Áudio encerrado; vídeo permanece independente')
                    return
            except OSError:
                self._set_state('unavailable', 'Saída local indisponível')
            finally:
                input_done.set(); self.fanout.unsubscribe(stream)
                terminate_media_process(proc)
                if writer is not None: writer.join(1)
                self._process = None
        if not self._stop.is_set():
            self._set_state('no_audio', 'Faixa de áudio não confirmada')
            self._push(self.status, 'Áudio gravado não confirmado; vídeo preservado')

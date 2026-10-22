"""Local listening through the isolated Cloud SDK, with the existing volume control."""
import os
import select
import shutil
import subprocess
import threading
import time
from urllib.parse import parse_qs,urlparse
from .live import LiveAudioSession,ffmpeg_audio_output_devices,audio_filter_for_slider,sanitize_text
from .intelbras_cloud import BridgeProcess,parse_bridge_route,_event_error
from .media_process import terminate_media_process


class IntelbrasCloudAudioSession(LiveAudioSession):
    def __init__(self,*args,sdk_dir=None,**kwargs):
        super().__init__(*args,**kwargs)
        self._route(self.url)
        self._sdk_dir=sdk_dir
        self._bridge=None

    def _route(self,url):
        return parse_bridge_route(url)

    def _sdk_options(self,url):
        return {}

    def stop(self):
        self._stop.set()
        if self._bridge is not None:self._bridge.request_stop()
        super().stop()

    def _commands(self,*_args):
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg:return []
        outputs=ffmpeg_audio_output_devices()
        gain='volume=1.000' if shutil.which('pactl') else audio_filter_for_slider(self.volume)
        return [('FFmpeg/'+backend,[ffmpeg,'-nostdin','-hide_banner','-loglevel','warning',
            '-probesize','1048576','-analyzeduration','1000000','-i','pipe:0','-map','0:a:0',
            '-vn','-sn','-dn','-af',gain,'-acodec','pcm_s16le','-progress','pipe:2','-stats_period','0.2',
            '-f',backend,'default']) for backend in ('pulse','alsa') if backend in outputs]

    def _run(self):
        from .intelbras_wine import wine_manager
        port,serial,channel=self._route(self.url)
        query=parse_qs(urlparse(self.url).query)
        window={key:query[key][0] for key in ('start','end')} if 'start' in query else None
        lease=None
        try:
            if self.url.startswith('intelbras-wine:'):
                self._push(self.status,'Áudio: preparando túnel Cloud…')
                lease=wine_manager().acquire(serial,port,cancel_event=self._stop)
                port=lease.port
            commands=self._commands(self.url)
            if not commands:
                self._set_state('unavailable','FFmpeg sem saída Pulse/ALSA')
                self._push(self.status,'Áudio: saída Pulse/PipeWire ou ALSA ausente');return
            for backend,command in commands:
                if self._stop.is_set():break
                read,write=os.pipe();client=proc=None
                try:
                    proc=subprocess.Popen(command,stdin=read,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,close_fds=True)
                    with self._process_lock:self._process=proc
                    os.close(read);read=-1
                    client=BridgeProcess(port,serial,self.username,self.password,sdk_dir=self._sdk_dir,media_fd=write,channel=channel,stream='main',playback_window=window,playback_speed=self.playback_speed,**self._sdk_options(self.url))
                    self._bridge=client;os.close(write);write=-1
                    deadline=time.monotonic()+15
                    buffer=bytearray();confirmed=False
                    while not self._stop.is_set() and proc.poll() is None:
                        client.poll_events()
                        if client.process.poll() is not None:break
                        if not confirmed and time.monotonic()>deadline:break
                        if not select.select([proc.stderr],[],[],.1)[0]:continue
                        raw=os.read(proc.stderr.fileno(),8192)
                        if not raw:break
                        buffer.extend(raw)
                        while b'\n' in buffer:
                            line,_,rest=buffer.partition(b'\n');buffer[:]=rest
                            text=line.decode('utf-8','replace').strip()
                            if text.startswith(('out_time_us=','out_time_ms=')):
                                try:positive=int(text.split('=',1)[1])>0
                                except ValueError:positive=False
                                if positive and not confirmed:
                                    confirmed=True;self._had_audio=True;self.detected_url=self.url
                                    self.current_backend=backend;self._set_state('active','',backend)
                                    self._push(self.status,'🔊 Áudio decodificado • Cloud • '+backend)
                                    if shutil.which('pactl'):self._attach_dynamic_volume_async(proc.pid)
                            elif '=' not in text and text:
                                self._push(self.diagnostics,sanitize_text(text,self.username,self.password))
                    if confirmed:
                        if not self._stop.is_set():self._set_state('unavailable','Áudio encerrado')
                        return
                    if any(v.get('stage') in {'login_failed','identity_mismatch'} for v in client.events):
                        self._set_state('authentication');self._push(self.status,_event_error(client.events));return
                finally:
                    if client is not None:client.close()
                    self._bridge=None
                    terminate_media_process(proc);self._process=None
                    for fd in (read,write):
                        if fd>=0:os.close(fd)
            if not self._stop.is_set():
                self._set_state('no_audio','Nenhuma faixa decodificada')
                self._push(self.status,'Áudio Cloud não confirmado: confira se o canal possui áudio habilitado no DVR.')
        except (ValueError,OSError) as exc:
            self._set_state('unavailable');self._push(self.status,'Áudio Cloud indisponível')
            self._push(self.diagnostics,sanitize_text(str(exc),self.username,self.password))
        finally:
            if lease is not None:lease.release()

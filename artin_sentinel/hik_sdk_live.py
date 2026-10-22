"""Hikvision SDK frames inside the existing Live View/playback surfaces."""
import os
import shutil
import subprocess
import threading
import time
from .live import LiveStreamSession,FramePacket,FRAME_SIZE,FRAME_WIDTH,FRAME_HEIGHT
from .media_process import terminate_media_process
from .hik_sdk import Client,parse_route

class HikSDKLiveSession(LiveStreamSession):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.options=parse_route(self.url);self.client=None;self._completed_source=False
        self.active_transport='Hikvision SDK local'
        self.frame_width=1280 if self.options['stream']=='main' else 640
        self.frame_height=720 if self.options['stream']=='main' else 360
        if self.playback:self.options['speed']=self.playback_speed
    def stop(self):
        self._stop.set()
        if self.client:self.client.request_stop()
        super().stop()
    def _command(self,url,transport='tcp'):
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg:raise ValueError('FFmpeg indisponível.')
        vf=(f'setpts=PTS/{self.playback_speed:g},' if self.playback else '')+f'scale={self.frame_width}:{self.frame_height}:force_original_aspect_ratio=decrease,pad={self.frame_width}:{self.frame_height}:(ow-iw)/2:(oh-ih)/2,fps={self.fps}'
        return [ffmpeg,'-nostdin','-hide_banner','-nostats','-loglevel','info',
            *(['-progress','pipe:2','-stats_period','0.25','-readrate',str(self.playback_speed)] if self.playback else []),
            '-probesize','1048576','-analyzeduration','1000000','-i','pipe:0','-map','0:v:0','-an','-sn','-dn',
            '-vf',vf,'-pix_fmt','rgb24','-f','rawvideo','pipe:1']
    def _events(self):
        for event in self.client.poll_events():
            stage=event['stage']
            if stage=='login_ok':self._push_diag('Hikvision SDK • login local OK • identidade não comparada por serial')
            elif stage in ('error','login_failed'):
                self._push_diag('Hikvision SDK • '+event.get('operation',stage)+' • código '+str(event.get('code','—')))
                self.last_error_class='sdk_login' if stage=='login_failed' else 'sdk_stream'
            elif stage in ('stream_closed','logout','cleanup') and not event.get('ok',True):
                self._push_diag('Hikvision SDK • encerramento não confirmado: '+stage)
            elif stage=='speed_accepted':self._push_diag(f"Hikvision SDK • velocidade aceita pelo DVR: {event['speed']:g}×; confirmar avanço medido")
            elif stage=='playback_complete':self._completed_source=True
            elif stage=='media_summary':self._push_diag(f"Hikvision SDK • {event['bytes']} bytes / {event['packets']} pacotes • pico {event['peak']} bytes")
    def _run(self):
        self.attempts=1;reader=None;proc=None;read,write=os.pipe();started=time.monotonic()
        try:
            proc=subprocess.Popen(self._command(self.url),stdin=read,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,close_fds=True)
            if not self._adopt_process(proc):return
            os.close(read);read=-1
            reader=threading.Thread(target=self._stderr_reader,args=(proc.stderr,self.profile_name),daemon=True);reader.start()
            self.client=Client(self.options,self.username,self.password,media_fd=write)
            os.close(write);write=-1
            self._push_status('Abrindo Hikvision SDK local…')
            while not self._stop.is_set():
                self._events()
                raw=self._read_exact(proc.stdout,self.frame_width*self.frame_height*3,self._stop,inactivity_timeout=25)
                self._events()
                if len(raw)!=self.frame_width*self.frame_height*3:break
                if not self.ever_had_frame:
                    self._push_diag(f'Hikvision SDK • primeiro quadro em {time.monotonic()-started:.2f}s')
                    self._push_status('● '+(f'REPRODUÇÃO {self.playback_speed:g}× • em validação' if self.playback else 'AO VIVO')+' • Hikvision SDK local')
                    self.ever_had_frame=True
                self._push_frame(FramePacket(raw,self.frame_width,self.frame_height))
        except (OSError,ValueError) as error:
            self._push_diag(str(error) if isinstance(error,ValueError) else 'Não foi possível abrir processo de mídia SDK.')
        finally:
            if self.client:self.client.close();self._events()
            for fd in (read,write):
                if fd>=0:os.close(fd)
            terminate_media_process(proc)
            self._process=None
            if reader:reader.join(timeout=.5)
            if not self._stop.is_set():
                self.current_state='completed' if self._completed_source and self.ever_had_frame else 'unavailable'
                self._push_status('Fim do trecho • Hikvision SDK local' if self.current_state=='completed' else 'SDK encerrado • consulte Diagnóstico')

"""Pilot consumer for a SIM Next tunnel opened outside Sentinel.

No Cloud keys, account tokens or tunnel creation occur here. The native SDK
runs in a fresh process. Credentials, media and events use separate pipes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import array
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlparse

from .live import LiveStreamSession, FramePacket, FRAME_WIDTH, FRAME_HEIGHT, FRAME_SIZE
from .media_process import terminate_media_process

ACCESS_CLOUD_BRIDGE = 'intelbras_cloud_bridge'


def normalize_serial(value: str) -> str:
    value = str(value or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9_-]{4,47}', value):
        raise ValueError('Informe um serial Intelbras válido, de 4 a 47 caracteres.')
    return value


def bridge_route(port: int, serial: str, channel: int, *, stream='main') -> str:
    if isinstance(port, bool) or not 1 <= int(port) <= 65535:
        raise ValueError('Porta local inválida.')
    if not 1 <= int(channel) <= 256:
        raise ValueError('Canal inválido.')
    if stream not in {'main','sub'}:raise ValueError('Perfil de vídeo inválido.')
    query={'serial':normalize_serial(serial)}
    if stream=='sub':query['stream']='sub'
    return f'intelbras-cloud://127.0.0.1:{int(port)}/{int(channel)}?{urlencode(query)}'


def parse_bridge_route(url: str) -> tuple[int, str, int]:
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
        if (parsed.scheme not in {'intelbras-cloud','intelbras-wine'} or parsed.hostname != '127.0.0.1'
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or set(query) not in ({'serial'},{'serial','stream'},{'serial','start','end'}) or len(query['serial']) != 1
                or ('stream' in query and query['stream'] not in (['main'],['sub']))
                or not re.fullmatch(r'/[0-9]{1,3}', parsed.path)):
            raise ValueError
        if 'start' in query:
            from datetime import datetime
            if len(query['start'])!=1 or len(query['end'])!=1:raise ValueError
            begin,end=(datetime.fromisoformat(query[key][0]) for key in ('start','end'))
            if begin.tzinfo is not None or end.tzinfo is not None or end<=begin or (end-begin).total_seconds()>86400:raise ValueError
        port, serial, channel = parsed.port, normalize_serial(query['serial'][0]), int(parsed.path[1:])
        if port is None:
            raise ValueError
        bridge_route(port, serial, channel)
        return port, serial, channel
    except (ValueError, TypeError, KeyError):
        raise ValueError('Rota da ponte Intelbras inválida; use o cadastro Cloud do Sentinel.') from None


def is_cloud_device(device) -> bool:
    try:
        metadata = json.loads(device['metadata_json'] or '{}')
        return isinstance(metadata, dict) and metadata.get('connection_mode') == ACCESS_CLOUD_BRIDGE
    except (TypeError, KeyError, IndexError, ValueError):
        return False


def default_sdk_dir() -> Path:
    from .intelbras_netsdk import vendor_install_directory
    return vendor_install_directory()


class BridgeProcess:
    """Own exactly one SDK process and its private IPC channels."""

    def __init__(self, port, serial, username, password, *, sdk_dir=None, media_fd=None, channel=1, stream='main', record_query=None, playback_window=None, host='127.0.0.1', login_mode=19, playback_speed=1.0, report_progress=False, persistent=False):
        bridge_route(port, serial or 'UNCONFIRMED', channel,stream=stream)
        if login_mode not in {0,19} or (login_mode==19 and (host!='127.0.0.1' or not serial)):
            raise ValueError('Modo ou destino do SDK inválido.')
        for value in (username, password):
            if not isinstance(value, str) or not value or '\0' in value or len(value.encode()) > 1024:
                raise ValueError('Credencial vazia ou inválida; valor omitido.')
        root = Path(sdk_dir or default_sdk_dir()).expanduser().resolve()
        if not (root / 'libdhnetsdk.so').is_file():
            raise ValueError('NetSDK Linux não encontrado. Instale o SDK Intelbras no Sentinel.')
        self._lock = threading.RLock()
        self._buffer = bytearray()
        self.events = []
        self.process = None
        self.control_socket = None
        self._idle = False
        self.event_fd = self.cancel_fd = -1
        self._work = tempfile.TemporaryDirectory(prefix='as-intelbras-cloud-')
        event_read, event_write = os.pipe()
        cancel_read, cancel_write = os.pipe()
        request = dict(sdk_dir=str(root), port=int(port), mode=login_mode, host=host, expected_serial=normalize_serial(serial) if serial else '',
                       username=username, password=password)
        if record_query is not None:request['record_query']=record_query
        if media_fd is not None:
            request['video'] = dict(media_fd=int(media_fd), cancel_fd=cancel_read, channel=int(channel), stream=stream)
            if playback_window:
                request['video']['playback']=playback_window
                request['video']['playback_speed']=float(playback_speed)
                if report_progress: request['video']['report_progress']=True
        env = os.environ.copy()
        env['LD_LIBRARY_PATH'] = str(root)
        control_child = None
        try:
            if persistent:
                if record_query is None and (not playback_window or media_fd is None):
                    raise ValueError('Sessão persistente exige reprodução ou consulta.')
                self.control_socket, control_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                request['control_fd'] = control_child.fileno()
            worker = Path(__file__).with_name('intelbras_cloud_worker.py')
            self.process = subprocess.Popen(
                [sys.executable, '-I', '-S', str(worker), '--worker', str(event_write)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                pass_fds=(event_write, cancel_read) + ((media_fd,) if media_fd is not None else ()) + ((control_child.fileno(),) if control_child else ()),
                env=env, cwd=self._work.name, start_new_session=True, close_fds=True,
            )
            self.event_fd, self.cancel_fd = event_read, cancel_write
            event_read = cancel_write = -1
            os.set_blocking(self.event_fd, False)
            self.process.stdin.write(json.dumps(request).encode())
            self.process.stdin.close()
        except Exception:
            self.close()
            raise ValueError('Não foi possível iniciar o processo isolado do NetSDK.') from None
        finally:
            if control_child is not None: control_child.close()
            for fd in (event_read, event_write, cancel_read, cancel_write):
                if fd >= 0:
                    os.close(fd)

    def poll_events(self):
        with self._lock:
            if self.event_fd < 0:
                return []
            while True:
                try:
                    chunk = os.read(self.event_fd, 4096)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                self._buffer.extend(chunk)
                if len(self._buffer) > 65536:
                    raise ValueError('Canal de eventos do processo excedeu o limite.')
            fresh = []
            while b'\n' in self._buffer:
                raw, _, remaining = self._buffer.partition(b'\n')
                self._buffer = bytearray(remaining)
                event = json.loads(raw)
                if not isinstance(event, dict) or not isinstance(event.get('stage'), str):
                    raise ValueError('Evento inválido do processo isolado.')
                fresh.append(event)
            self.events.extend(fresh)
            del self.events[:-64]
            if any(event['stage']=='session_idle' for event in fresh):self._idle=True
            return fresh

    def wait_idle(self, timeout=4):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.poll_events()
            if self._idle and self.process.poll() is None:return True
            if self.process.poll() is not None:return False
            time.sleep(.02)
        return False

    def resume_playback(self, media_fd, *, channel, stream, playback_window, playback_speed=1):
        with self._lock:
            if not self._idle or self.control_socket is None or self.process.poll() is not None:
                raise ValueError('Sessão de reprodução indisponível.')
            read,write=os.pipe()
            options=dict(channel=channel,stream=stream,playback=playback_window,playback_speed=playback_speed)
            try:
                self.control_socket.sendmsg([json.dumps(options).encode()],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[media_fd,read]))])
                self.cancel_fd=write;write=-1
                self.events.clear();self._idle=False
            finally:
                os.close(read)
                if write>=0:os.close(write)

    def retarget_playback(self, media_fd, *, at, speed, ident):
        with self._lock:
            if self._idle or self.control_socket is None or self.process.poll() is not None:
                raise ValueError('Fluxo indisponível para salto.')
            payload=dict(action='retarget',at=at,speed=float(speed),id=int(ident))
            self.control_socket.sendmsg([json.dumps(payload).encode()],
                [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[media_fd]))])

    def resume_query(self, query):
        with self._lock:
            if not self._idle or self.control_socket is None or self.process.poll() is not None:
                raise ValueError('Sessão de consulta indisponível.')
            self.control_socket.send(json.dumps({'record_query':query}).encode())
            self.events.clear();self._idle=False

    def request_stop(self):
        with self._lock:
            if self.cancel_fd >= 0:
                os.close(self.cancel_fd)
                self.cancel_fd = -1

    def close(self):
        self.request_stop()
        if self.control_socket is not None:
            self.control_socket.close()
            self.control_socket=None
        process = self.process
        if process is not None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=0.3)
                        break
                    except subprocess.TimeoutExpired:
                        pass
        with self._lock:
            if self.event_fd >= 0:
                try:
                    self.poll_events()
                finally:
                    os.close(self.event_fd)
                    self.event_fd = -1
        self._work.cleanup()


def _event_error(events) -> str:
    stages = {event.get('stage') for event in events}
    if 'identity_mismatch' in stages:
        return 'O serial retornado pelo DVR não corresponde ao cadastro. Confira a porta da ponte.'
    if 'login_failed' in stages:
        event = next(e for e in events if e.get('stage') == 'login_failed')
        return f'Login não concluído: código {int(event.get("login_error", 0))}; SDK 0x{int(event.get("sdk_error", 0)):08X}. Nenhuma repetição automática.'
    if 'record_search_failed' in stages:
        return 'O DVR não concluiu a consulta de gravações pelo SDK. Confira permissão, horário e período.'
    if stages & {'cleanup_exception', 'logout_failed', 'stream_stop_failed'}:
        return 'O processo NetSDK não confirmou o encerramento completo.'
    if 'channel_invalid' in stages:
        return 'O canal não pertence ao inventário anunciado pelo DVR.'
    return 'O processo isolado do NetSDK não concluiu a operação; consulte a ponte e o SDK instalado.'


def probe_bridge(port, serial, username, password, *, sdk_dir=None, cancel_event=None, timeout=20):
    if cancel_event is not None and cancel_event.is_set():
        raise ValueError('Conexão cancelada pelo usuário.')
    client = BridgeProcess(port, serial, username, password, sdk_dir=sdk_dir)
    expired = cancelled = False
    try:
        deadline = time.monotonic() + timeout
        while client.process.poll() is None:
            client.poll_events()
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            if time.monotonic() >= deadline:
                expired = True
                break
            time.sleep(0.02)
    finally:
        client.close()
    if cancelled:
        raise ValueError('Conexão cancelada pelo usuário.')
    if expired:
        raise ValueError('O processo isolado excedeu o prazo e foi encerrado.')
    login = next((e for e in client.events if e.get('stage') == 'login_ok'), None)
    if client.process.returncode != 0 or not login or not any(e.get('stage') == 'cleanup_returned' for e in client.events):
        raise ValueError(_event_error(client.events))
    return dict(channels=int(login['channels']), serial_verified=True)


def register_bridge_inventory(db, site_id, name, serial, port, channels, *, managed=False):
    from .domain import Device, DeviceKind, DeviceStatus
    from .recorder import RecorderChannel
    serial = normalize_serial(serial)
    if not 1 <= int(channels) <= 256:
        raise ValueError('Inventário de canais inválido.')
    bridge_route(port, serial, 1)
    prior = db.find_device_by_site_ip(site_id, serial)
    if prior is not None and not is_cloud_device(prior):
        raise ValueError('Esse identificador já pertence a outro cadastro no Site.')
    metadata = dict(connection_mode=ACCESS_CLOUD_BRIDGE, recorder_protocol='intelbras',
                    cloud_serial=serial, bridge_port=int(port), wine_managed=bool(managed), canonical_type='xvr',
                    identity_source='authenticated_cloud_inventory')
    device = Device(site_id=site_id, name=name.strip() or 'DVR Intelbras Cloud', ip=serial,
                    serial=serial, manufacturer='Intelbras', model=prior['model'] if prior is not None else '',
                    kind=DeviceKind.XVR,
                    provider='intelbras', status=DeviceStatus.ONLINE, metadata=metadata)
    did = db.upsert_device(device)
    db.update_device_identity(did, device.name, 'xvr', 'Intelbras', device.model)
    if db.get_device(did)['archived']:
        db.archive_device(did, False)
    old_channels = {ch['channel_no']: ch for ch in db.list_recorder_channels(did)}
    inventory = []
    for number in range(1, int(channels) + 1):
        route = bridge_route(port, serial, number)
        if managed:route=route.replace('intelbras-cloud://','intelbras-wine://',1)
        sub=bridge_route(port,serial,number,stream='sub')
        if managed:sub=sub.replace('intelbras-cloud://','intelbras-wine://',1)
        old = old_channels.get(number)
        confirmed = bool(old and old['main_rtsp_url'] == route and old['available'])
        inventory.append(RecorderChannel(number, f'Canal {number:02d}', route, confirmed,
            main_rtsp_url=route, sub_rtsp_url=sub, audio_mode='unknown', detail=('Vídeo confirmado via ponte Intelbras Cloud' if confirmed
            else 'Inventariado pelo NetSDK; abra o canal para confirmar imagem.')))
    db.replace_recorder_channels(did, inventory)
    return did


def upgrade_cloud_inventory(db):
    """Backfill saved pilot routes locally, without network or identity guesses."""
    for device in db.list_devices(include_archived=True):
        if not is_cloud_device(device):continue
        metadata=json.loads(device['metadata_json'])
        for channel in db.list_recorder_channels(device['id']):
            try:
                port,serial,number=parse_bridge_route(channel['main_rtsp_url'])
                if (port!=metadata.get('bridge_port') or serial!=metadata.get('cloud_serial') or number!=channel['channel_no']):continue
            except ValueError:continue
            if not channel['sub_rtsp_url']:
                sub=bridge_route(port,serial,number,stream='sub')
                if channel['main_rtsp_url'].startswith('intelbras-wine:'):sub=sub.replace('intelbras-cloud:','intelbras-wine:',1)
                db.conn.execute("UPDATE recorder_channels SET sub_rtsp_url=?,audio_mode='unknown' WHERE id=?",(sub,channel['id']))
        if device['canonical_type']=='unknown':
            db.conn.execute("UPDATE devices SET canonical_type='xvr' WHERE id=?",(device['id'],))
    db.conn.commit()


class IntelbrasCloudLiveSession(LiveStreamSession):
    """Decode compressed callback data into the existing mosaic frame queue."""

    def __init__(self, *args, sdk_dir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._route(self.url)
        self._sdk_dir = sdk_dir
        self._bridge_process = None
        self._seek_lock=threading.Lock()
        self._seek_request=None
        self._seek_busy=False
        self._retarget_result=None
        self._retarget_ident=0
        self._native_window=None
        self._native_seek_available=False
        from .shared_playback_audio import PlaybackFanout
        self._playback_fanout = PlaybackFanout() if self.playback else None
        self.active_transport = 'Cloud via Wine' if self.url.startswith('intelbras-wine:') else 'Cloud via ponte'

    def request_playback_seek(self, url, speed):
        """True=queued; None=busy; False=use the established reopen path."""
        from datetime import datetime
        if not self.playback or not self._native_seek_available or self._stop.is_set() or self.current_state!='playing':return False
        if self._playback_fanout is None or self._playback_fanout.subscriber is not None:return False
        try:
            if self._route(url)!=self._route(self.url) or urlparse(url).netloc!=urlparse(self.url).netloc:return False
            query=parse_qs(urlparse(url).query)
            at=query['start'][0];target=datetime.fromisoformat(at)
            if not self._native_window:return False
            first,last=(datetime.fromisoformat(self._native_window[k]) for k in ('start','end'))
            if not first<=target<last or float(speed) not in (.5,1,2,4,8,16):return False
        except (ValueError,KeyError,TypeError):return False
        with self._seek_lock:
            if self._seek_busy:return None
            self._seek_busy=True;self._seek_request=(url,at,float(speed))
        self.latest_frame()
        return True

    @property
    def playback_position_seconds(self):
        if self._seek_busy:return None
        return super().playback_position_seconds

    def _retarget_decoder(self, client, old_proc, old_reader, request, profile):
        from .shared_playback_audio import PlaybackFanout
        from .playback_clock import PlaybackClock
        url,at,speed=request
        read,write=os.pipe();decode_read,decode_write=os.pipe()
        fanout=PlaybackFanout();fanout.start(read,decode_write)
        proc=None
        try:
            # Command generation uses the requested speed; old reader is stopped
            # before the new playback clock is installed.
            self.playback_speed=speed
            proc=subprocess.Popen(self._command(url),stdin=decode_read,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,bufsize=0,close_fds=True)
            os.close(decode_read);decode_read=-1
            self._retarget_ident+=1;ident=self._retarget_ident;self._retarget_result=None
            client.retarget_playback(write,at=at,speed=speed,ident=ident)
            os.close(write);write=-1
            deadline=time.monotonic()+4
            while not self._stop.is_set() and time.monotonic()<deadline:
                self._handle_events(client)
                if self._retarget_result is not None:break
                if client.process.poll() is not None:break
                self._stop.wait(.02)
            if self._stop.is_set() or self._retarget_result!=(ident,True):
                raise ValueError('Salto não confirmado; use Parar e Reproduzir.')
            terminate_media_process(old_proc)
            if old_reader:old_reader.join(.5)
            self._playback_fanout.close()
            self._playback_fanout=fanout
            self.playback_clock=PlaybackClock(speed)
            self.latest_frame();self.ever_had_frame=False
            self.active_url=url
            if not self._adopt_process(proc):raise ValueError('Reprodução cancelada.')
            reader=threading.Thread(target=self._stderr_reader,args=(proc.stderr,profile),daemon=True)
            reader.start()
            self._push_diag('NetSDK • salto no mesmo fluxo • sem novo login ou abertura de reprodução')
            self._push_status('Atualizando imagem • sessão do DVR mantida…')
            return proc,reader
        except Exception:
            fanout.close();terminate_media_process(proc)
            raise
        finally:
            for fd in (write,decode_read):
                if fd>=0:os.close(fd)

    def create_recording_audio(self, *, volume=100):
        if not self.playback: raise ValueError("Abra uma gravação antes de ouvir")
        from .shared_playback_audio import SharedPlaybackAudioSession
        return SharedPlaybackAudioSession(self, volume=volume)

    def _route(self,url):
        return parse_bridge_route(url)

    def _sdk_options(self,url):
        return {}

    def stop(self):
        self._stop.set()
        bridge = self._bridge_process
        if bridge is not None:
            bridge.request_stop()
        super().stop()

    def _command(self, url, transport='tcp'):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise FileNotFoundError('FFmpeg não encontrado')
        vf = (f'scale={FRAME_WIDTH}:{FRAME_HEIGHT}:force_original_aspect_ratio=decrease,'
              f'pad={FRAME_WIDTH}:{FRAME_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={self.fps}')
        if self.playback:
            vf = (f'setpts=(PTS-STARTPTS)/{self.playback_speed:g},fps={self.fps},'
                  f'scale={FRAME_WIDTH}:{FRAME_HEIGHT}:force_original_aspect_ratio=decrease,'
                  f'pad={FRAME_WIDTH}:{FRAME_HEIGHT}:(ow-iw)/2:(oh-ih)/2')
        return [ffmpeg, '-nostdin', '-hide_banner', '-nostats', '-loglevel', 'info',
                *(['-progress','pipe:2','-stats_period','0.25'] if self.playback else []),
                '-probesize', '1048576', '-analyzeduration', '1000000',
                *(['-skip_frame','noref'] if self.playback and self.playback_speed>=8 else []),
                *(['-readrate',f'{self.playback_speed:g}'] if self.playback else []), '-i', 'pipe:0',
                '-map', '0:v:0', '-an', '-sn', '-dn', '-vf', vf,
                '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1']

    def _handle_events(self, client):
        for event in client.poll_events():
            stage = event.get('stage')
            if stage in {'login_failed', 'identity_mismatch', 'worker_exception', 'inventory_invalid'}:
                self.last_error_class = 'identity' if stage == 'identity_mismatch' else 'sdk_login'
                self._authentication_failure.set()
                self._push_diag(_event_error(client.events))
                self._push_status('Conexão interrompida • confira o acesso Cloud')
            elif stage == 'login_ok':
                self._push_diag('NetSDK • login OK • '+('serial conferido' if event.get('serial_verified') else 'serial não informado')+' • modo '+str(event.get('mode',19)))
            elif stage == 'stream_started':
                self._native_seek_available=bool(event.get('native_seek',False))
            elif stage == 'session_reused':
                self._push_diag('NetSDK • sessão autenticada reutilizada • sem novo login')
            elif stage in {'playback_retargeted','playback_retarget_failed'}:
                self._retarget_result=(event.get('id'),stage=='playback_retargeted')
                if stage=='playback_retarget_failed':
                    self._push_diag('NetSDK • salto recusado; sem repetição automática')
            elif stage == 'playback_speed_applied':
                self.effective_playback_speed=float(event['speed'])
                self._push_diag(f'NetSDK • comando de velocidade aceito: {self.effective_playback_speed:g}×; medindo avanço da mídia')
            elif stage == 'playback_speed_failed':
                self.speed_rejected=True
                self._push_status('Velocidade recusada pelo DVR • selecione 1× e Reproduzir')
                self._push_diag('NetSDK • velocidade recusada; reprodução interrompida. Selecione 1× e consulte o diagnóstico.')
            elif stage in {'playback_flow_paused','playback_flow_resumed'}:
                action='pausado para drenar' if stage.endswith('paused') else 'retomado'
                self._push_diag(f"NetSDK • fluxo {action} • fila {int(event.get('queued',0))} pacotes / {int(event.get('buffered',0))} bytes")
            elif stage == 'stream_summary':
                self._push_diag(f"NetSDK • resumo: {int(event.get('bytes',0))} bytes, {int(event.get('packets',0))} pacotes; pico {int(event.get('buffer_peak',0))} bytes")
            elif stage in {'stream_open_failed', 'callback_failed', 'stream_error'}:
                self._push_diag('NetSDK • falha no stream • ' + str(stage)+' • '+str(event.get('reason','sem detalhe')))

    def _attempt_profile(self, url, profile, transport='tcp'):
        if self._stop.is_set():
            return False
        self.attempts += 1
        self.current_state = 'connecting'
        started=time.monotonic()
        self.active_profile=profile
        self.active_url=url
        stream=parse_qs(urlparse(url).query).get('stream',['main'])[0]
        self._push_status('Preparando '+self.active_transport+' • '+profile+'…')
        port, serial, channel = self._route(url)
        client = proc = reader = lease = None
        media_read, media_write = os.pipe()
        got = False
        try:
            if url.startswith('intelbras-wine:'):
                from .intelbras_wine import wine_manager
                lease=wine_manager().acquire(serial,port,cancel_event=self._stop,progress=self._push_status)
                port=lease.port
            self._push_diag(f'{profile}: túnel disponível em {time.monotonic()-started:.2f} s; preparando sessão e mídia')
            if self._playback_fanout is not None:
                decoder_read, decoder_write = os.pipe()
                self._playback_fanout.start(media_read, decoder_write)
                media_read = decoder_read
            proc = subprocess.Popen(self._command(url), stdin=media_read, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, bufsize=0, close_fds=True)
            if not self._adopt_process(proc) or self._stop.is_set():
                return False
            os.close(media_read)
            media_read = -1
            query=parse_qs(urlparse(url).query)
            window={key:query[key][0] for key in ('start','end')} if 'start' in query else None
            self._native_window=window
            options=dict(sdk_dir=self._sdk_dir, media_fd=media_write, channel=channel, stream=stream,
                         playback_window=window, playback_speed=self.playback_speed, **self._sdk_options(url))
            if self.playback:
                from .playback_session_pool import playback_pool
                client=playback_pool().acquire(port,serial,self.username,self.password,cancel_event=self._stop,**options)
            else:
                client=BridgeProcess(port,serial,self.username,self.password,**options)
            self._bridge_process = client
            if self._stop.is_set():
                client.request_stop()
            os.close(media_write)
            media_write = -1
            reader = threading.Thread(target=self._stderr_reader, args=(proc.stderr, profile), daemon=True)
            reader.start()
            while not self._stop.is_set():
                with self._seek_lock:
                    request=self._seek_request;self._seek_request=None
                if request is not None:
                    proc,reader=self._retarget_decoder(client,proc,reader,request,profile)
                    got=False;started=time.monotonic()
                self._handle_events(client)
                raw = self._read_exact(proc.stdout, FRAME_SIZE, self._stop, inactivity_timeout=15)
                self._handle_events(client)
                if len(raw) != FRAME_SIZE:
                    break
                if not got:
                    got = True
                    self.ever_had_frame = True
                    self._push_diag(f'{profile}: primeiro quadro em {time.monotonic()-started:.2f} s')
                    self._push_status('● AO VIVO • '+profile+' • '+self.active_transport)
                with self._seek_lock:
                    # Discard a frame assembled while the UI queued a jump.
                    if self._seek_request is not None:continue
                    self._seek_busy=False
                    self._push_frame(FramePacket(raw))
        except (OSError, ValueError) as exc:
            self._push_diag(str(exc) if lease is None and url.startswith('intelbras-wine:') else f'Ponte Intelbras: {type(exc).__name__}')
            self._push_status('Ponte indisponível • consulte Diagnóstico')
        finally:
            if self.playback and client is not None:
                # Quiesce native callbacks before closing the old media transport.
                client.close()
            if self._playback_fanout is not None: self._playback_fanout.close()
            for fd in (media_read, media_write):
                if fd >= 0:
                    os.close(fd)
            if client is not None:
                client.close()
                if client.process.returncode not in (0, None) and not self._stop.is_set():
                    self._push_diag(_event_error(client.events))
            self._bridge_process = None
            terminate_media_process(proc)
            self._process = None
            if reader is not None:
                reader.join(timeout=0.3)
            if lease is not None:lease.release()
        return got

    def _run(self):
        if not self.decoder_available:
            self.current_state = 'unavailable'
            self._push_status('FFmpeg não encontrado')
            return
        # Reconnect only after decoded video. Never retry a failed SDK login.
        for attempt in range(1 if self.playback else 3):
            got = self._attempt_profile(self.url, self.profile_name)
            if not got and self.fallback_url and not self._stop.is_set() and not self._authentication_failure.is_set():
                self._push_diag('Perfil sem vídeo; fallback → '+self.fallback_name)
                got=self._attempt_profile(self.fallback_url,self.fallback_name)
            if self._stop.is_set() or self._authentication_failure.is_set() or not got:
                break
            if not self.playback and attempt < 2:
                self.reconnects += 1
                self.current_state = 'retrying'
                self._push_status('Conexão interrompida • tentando recuperar a ponte…')
                if self._stop.wait((2, 5)[attempt]):
                    break
        if not self._stop.is_set():
            self.current_state = 'unavailable'

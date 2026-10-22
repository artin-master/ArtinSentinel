"""Bounded, cancellable SDK playback export. No frames or credentials on disk."""
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import math
import os
import select
import shutil
import subprocess
import tempfile
import time

from .recording_export import RecordingExportError
from .media_process import terminate_media_process


def export_cloud_mp4(url, username, password, destination, duration_seconds, *,
                      cancel=None, progress=None, include_audio=True, diagnostics=None, quality='original'):
    from .recording_export_profiles import validate_quality, video_args, audio_args
    validate_quality(quality)
    from .intelbras_cloud import BridgeProcess, parse_bridge_route
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    target = Path(destination)
    port, serial, channel = parse_bridge_route(url)
    query = parse_qs(urlparse(url).query)
    if set(query) != {'serial','start','end'}:
        raise RecordingExportError('Selecione uma gravação para exportar')
    window = {key:query[key][0] for key in ('start','end')}
    expected = (datetime.fromisoformat(window['end'])-datetime.fromisoformat(window['start'])).total_seconds()
    if (not ffmpeg or not ffprobe or target.suffix.lower() != '.mp4' or
            not 1 <= duration_seconds <= 86400 or abs(expected-duration_seconds) > .1):
        raise RecordingExportError('Exportação inválida ou FFmpeg/FFprobe indisponível')
    if target.exists(): raise RecordingExportError('O arquivo de destino já existe; escolha outro nome')
    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise RecordingExportError('Exportação cancelada')
    def update(message):
        if progress: progress(message)
    def diagnose(message):
        if diagnostics:
            from .live import sanitize_text
            clean = sanitize_text(str(message), username, password).replace(serial, '<omitido>')
            diagnostics(clean[:1500])
    check_cancel()
    diagnose(f'início • duração solicitada {duration_seconds}s • perfil {quality} • áudio '+('incluir' if include_audio else 'excluir'))
    fd, name = tempfile.mkstemp(prefix='.sentinel-export-',suffix='.mp4',dir=target.parent)
    os.close(fd)
    proc = client = lease = None
    read = write = -1
    try:
        update('Preparando conexão com o gravador…')
        if url.startswith('intelbras-wine:'):
            from .intelbras_wine import wine_manager
            lease = wine_manager().acquire(serial,port,cancel_event=cancel,progress=update)
            port = lease.port
        check_cancel()
        read, write = os.pipe()
        command = [ffmpeg,'-nostdin','-hide_banner','-loglevel','warning',
                   '-stats_period','0.5','-progress','pipe:1',
                   '-probesize','1048576','-analyzeduration','1000000',
                   '-i','pipe:0','-t',str(duration_seconds),'-map','0:v:0',
                   *audio_args(quality, include_audio), *video_args(quality),
                   '-movflags','+faststart','-f','mp4','-y',name]
        proc = subprocess.Popen(command,stdin=read,stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,close_fds=True)
        os.close(read); read = -1
        client = BridgeProcess(port,serial,username,password,media_fd=write,channel=channel,
                               playback_window=window,playback_speed=1,report_progress=True)
        os.close(write); write = -1
        os.set_blocking(proc.stdout.fileno(),False)
        os.set_blocking(proc.stderr.fileno(),False)
        began = last_input = last_output = time.monotonic()
        last_report = began-5
        received = written = frames = file_size = 0
        last_elapsed = 0.0
        buffer = bytearray(); err_buffer = bytearray(); errors = deque(maxlen=8)
        stderr_reports = suppressed = 0
        streams = {proc.stdout,proc.stderr}
        source_ended = None
        update('Recebendo gravação • 0%…')
        while proc.poll() is None:
            check_cancel()
            now = time.monotonic()
            if now-began > (max(180,duration_seconds*6+120) if quality=='compact' else max(120,duration_seconds*3+60)):
                raise RecordingExportError('Prazo total da exportação excedido; consulte o diagnóstico')
            if now-last_output > 60:
                state = ('Sem dados novos do DVR e sem avanço do MP4' if now-last_input > 60 else
                         'O SDK recebe dados, mas o MP4 não avança')
                diagnose(state+f' • recebidos={received} enviados={written} arquivo={file_size} quadros={frames} tempo={last_elapsed:.2f}s')
                raise RecordingExportError(state+' há 60 segundos; nenhum arquivo incompleto foi salvo')
            for event in client.poll_events():
                stage=event['stage']
                if stage=='stream_progress':
                    new_received=int(event.get('bytes',0));new_written=int(event.get('written',0))
                    if new_received>received: last_input=now
                    received,written=new_received,new_written
                elif stage not in {'playback_flow_paused','playback_flow_resumed'}:
                    # No native strings, names, addresses, serials or credentials.
                    diagnose('SDK • '+stage+(' • código '+hex(int(event['sdk_error'])) if 'sdk_error' in event else ''))
                if stage in {'login_failed','identity_mismatch','worker_exception','stream_open_failed','callback_failed'}:
                    raise RecordingExportError('O gravador interrompeu a exportação • '+stage)
                if stage=='stream_error':
                    diagnose('SDK • falha de mídia • '+str(event.get('reason','desconhecida')))
            for pipe in select.select(list(streams),[],[],.1)[0] if streams else ():
                chunk=os.read(pipe.fileno(),8192)
                if not chunk:
                    streams.discard(pipe);continue
                if pipe is proc.stderr:
                    err_buffer.extend(chunk)
                    while b'\n' in err_buffer:
                        line,_,rest=err_buffer.partition(b'\n');err_buffer[:]=rest
                        text=line.decode('utf-8','replace')[:1000]
                        if text.strip():
                            errors.append(text)
                            if stderr_reports < 8:
                                diagnose('FFmpeg • '+text);stderr_reports+=1
                            else:suppressed+=1
                    if len(err_buffer)>8192:del err_buffer[:-8192]
                    continue
                buffer.extend(chunk)
                while b'\n' in buffer:
                    line,_,rest = buffer.partition(b'\n'); buffer[:] = rest
                    if line.startswith(b'frame='):
                        try: value=int(line.split(b'=',1)[1])
                        except ValueError: continue
                        if value>frames:frames=value;last_output=now
                    elif line.startswith(b'out_time_us='):
                        try: elapsed = int(line.split(b'=',1)[1])/1_000_000
                        except ValueError: continue
                        if elapsed > last_elapsed:
                            last_output=now;last_elapsed=elapsed
                            update(f'Exportando gravação • {min(99,int(100*elapsed/duration_seconds))}%')
            size=Path(name).stat().st_size
            if size>file_size:file_size=size;last_output=now
            if now-last_report>=5:
                if suppressed:
                    diagnose(f'FFmpeg • {suppressed} avisos adicionais • último: '+errors[-1])
                    suppressed=0
                diagnose(f'andamento • recebidos={received}B enviados={written}B MP4={file_size}B quadros={frames} tempo={last_elapsed:.2f}s • {now-began:.0f}s decorridos')
                update(f'Exportando gravação • {min(99,int(100*last_elapsed/duration_seconds))}% • {now-began:.0f}s decorridos')
                last_report=now
            if client.process.poll() is not None:
                if source_ended is None:source_ended=now
                if now-source_ended>10:
                    raise RecordingExportError('O recebimento terminou, mas o MP4 não concluiu em 10 segundos')
        # Drain final error messages after the process exits; never lose a codec/mux failure.
        rest=proc.stderr.read() or b''
        for line in (bytes(err_buffer)+rest).decode('utf-8','replace').splitlines()[-8:]:
            if line.strip():diagnose('FFmpeg • '+line[:1000])
        diagnose(f'FFmpeg encerrado • código {proc.returncode} • MP4 temporário {Path(name).stat().st_size}B')
        check_cancel()
        if proc.returncode != 0:
            raise RecordingExportError('Não foi possível converter a gravação; confira o período e os codecs')
        update('Validando duração e conteúdo do MP4…')
        probe = subprocess.run([ffprobe,'-v','error','-show_streams','-show_format','-of','json',name],
                               capture_output=True,text=True,timeout=20,check=True)
        info = json.loads(probe.stdout)
        duration = float(info.get('format',{}).get('duration',0))
        diagnose(f'validação • duração obtida {duration:.3f}s / solicitada {duration_seconds}s • codecs '+','.join(str(v.get('codec_name','?')) for v in info.get('streams',[])))
        # Refuse a short/empty response rather than reporting a successful hour export.
        tolerance = min(2,max(.25,duration_seconds*.01))
        if (not math.isfinite(duration) or not any(s.get('codec_type')=='video' for s in info.get('streams',[])) or
                duration < duration_seconds-tolerance or duration > duration_seconds+2):
            raise RecordingExportError('O DVR não entregou todo o intervalo solicitado; reduza o recorte ou confira lacunas')
        check_cancel()
        os.link(name,target)
        sound = any(s.get('codec_type')=='audio' for s in info.get('streams',[]))
        update('Concluído • 100% • '+('com áudio' if sound else 'sem faixa de áudio'))
        diagnose(f'MP4 final publicado • {target.stat().st_size}B • '+('com áudio' if sound else 'sem áudio'))
        return target
    except FileExistsError as exc:
        raise RecordingExportError('O arquivo de destino já existe; escolha outro nome') from exc
    except RecordingExportError:
        raise
    except Exception as exc:
        raise RecordingExportError('Exportação interrompida • '+type(exc).__name__+'; nenhum arquivo incompleto publicado') from None
    finally:
        if client is not None:
            client.request_stop()
        terminate_media_process(proc)
        for descriptor in (read,write):
            if descriptor >= 0:
                try: os.close(descriptor)
                except OSError: pass
        if client is not None:
            # Give StopPlayBack/Logout/Cleanup their bounded drain window.
            until = time.monotonic()+5
            while client.process.poll() is None and time.monotonic()<until:
                try:client.poll_events()
                except (ValueError,OSError):break
                time.sleep(.02)
            client.close()
        if lease is not None: lease.release()
        Path(name).unlink(missing_ok=True)

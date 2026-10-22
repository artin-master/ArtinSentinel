"""Convert a recorder playback stream into an atomic local MP4 export."""

from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading
import re
import time
from collections import deque

from .live import authenticated_rtsp_url, ffmpeg_rtsp_timeout_args


class RecordingExportError(RuntimeError):
    pass


def validate_export_media(path,duration_seconds,native_events):
    """Validate before publication; a clean decoder EOF is not proof of a full clip."""
    import json
    ffprobe=shutil.which('ffprobe')
    if not ffprobe:raise RecordingExportError('FFprobe necessário para conferir o MP4 antes de salvar.')
    try:
        result=subprocess.run([ffprobe,'-v','error','-show_entries','format=duration:stream=codec_type,duration',
            '-of','json',str(path)],capture_output=True,text=True,timeout=15)
        data=json.loads(result.stdout);duration=float(data.get('format',{}).get('duration',0))
        video_durations=[float(stream.get('duration') or 0) for stream in data.get('streams',[]) if stream.get('codec_type')=='video']
        video_duration=max(video_durations,default=0)
        has_video=bool(video_durations)
    except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):
        raise RecordingExportError('Não foi possível validar o MP4 gerado.') from None
    coverage=min(duration,video_duration)
    if result.returncode or not has_video or coverage<max(.1,duration_seconds-max(.5,min(2,duration_seconds*.02))):
        raise RecordingExportError(f'MP4 incompleto: {coverage:.1f}s de vídeo recebidos para {duration_seconds}s solicitados.')
    failure=next((e for e in native_events if e.get('stage') in {'error','login_failed'} and e.get('operation')!='media_queue_or_pipe'),None)
    # FFmpeg closes its input after -t; the resulting SDK pipe closure is expected
    # only after duration/video have been validated. All other native failures block success.
    if failure and failure.get('operation')!='media_queue_or_pipe':
        raise RecordingExportError('SDK interrompeu a exportação: '+str(failure.get('operation',failure['stage'])))
    return duration


def export_mp4(url: str, username: str, password: str, destination: str,
               duration_seconds: int, *, cancel: threading.Event | None = None,
               progress=None, include_audio: bool = True, diagnostics=None, quality='original') -> Path:
    """Save only a completed conversion; never overwrite an existing export."""
    from .recording_export_profiles import validate_quality, video_args, audio_args
    validate_quality(quality)
    from urllib.parse import urlparse
    if urlparse(url).scheme in {'intelbras-cloud', 'intelbras-wine'}:
        from .cloud_recording_export import export_cloud_mp4
        return export_cloud_mp4(url, username, password, destination, duration_seconds,
                                cancel=cancel, progress=progress, include_audio=include_audio, diagnostics=diagnostics, quality=quality)

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
    errors = deque(maxlen=12)
    error_reader = None
    sdk_client=None;input_read=input_write=-1
    watchdog_done=threading.Event()
    watchdog_failure=[]
    try:
        sdk_route=urlparse(url).scheme=='hik-sdk'
        input_args=['-rtsp_transport','tcp',*ffmpeg_rtsp_timeout_args(),'-i',authenticated_rtsp_url(url,username,password)]
        if sdk_route:
            from .hik_sdk import parse_route,Client
            options=parse_route(url);options['speed']=1
            input_read,input_write=os.pipe()
            input_args=['-i','pipe:0']
        command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-stats_period", "1",
                   "-progress", "pipe:1", *input_args, "-t", str(duration_seconds),
                   "-map", "0:v:0",
                   *audio_args(quality, include_audio), *video_args(quality),
                   "-movflags", "+faststart", "-f", "mp4", "-y", tmp_name]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=input_read if sdk_route else subprocess.DEVNULL, text=True, close_fds=True)
        if sdk_route:
            os.close(input_read);input_read=-1
            sdk_client=Client(options,username,password,media_fd=input_write)
            os.close(input_write);input_write=-1
        def read_errors():
            for line in proc.stderr:
                line=re.sub(r'(?:rtsp|rtsps|https?)://\S+','<endereço omitido>',line)
                for secret in (password, username+':'+password):
                    if secret:line=line.replace(secret,'<omitido>')
                errors.append(line.strip()[:500])
        error_reader=threading.Thread(target=read_errors,daemon=True);error_reader.start()
        if diagnostics:diagnostics(('Exportação Hikvision SDK' if sdk_route else 'Exportação RTSP')+' • Original copia vídeo; Compacto recodifica • aguardando mídia do DVR')
        last_progress=[time.monotonic()]
        def terminate_export():
            try:
                proc.terminate()
                try:proc.wait(timeout=2)
                except subprocess.TimeoutExpired:proc.kill()
            except ProcessLookupError:pass
        def watchdog():
            deadline=time.monotonic()+max(90,duration_seconds*3+60)
            while not watchdog_done.wait(.2):
                if cancel is not None and cancel.is_set():terminate_export();return
                if time.monotonic()>deadline or time.monotonic()-last_progress[0]>60:
                    watchdog_failure.append('Sem progresso na exportação por 60 s ou prazo total excedido.');terminate_export();return
        threading.Thread(target=watchdog,daemon=True).start()
        assert proc.stdout is not None
        for line in proc.stdout:
            last_progress[0]=time.monotonic()
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
        if error_reader:error_reader.join(timeout=1)
        if cancel is not None and cancel.is_set():
            raise RecordingExportError("Exportação cancelada")
        if watchdog_failure:raise RecordingExportError(watchdog_failure[0])
        events=[]
        if sdk_client:
            events=sdk_client.poll_events()
            failure=next((e for e in events if e.get('stage') in {'error','login_failed'}),None)
            if failure and code!=0:errors.append('SDK: '+str(failure.get('operation',failure['stage']))+' código '+str(failure.get('code','—')))
        if code != 0 or Path(tmp_name).stat().st_size < 1024:
            raise RecordingExportError("O gravador ou FFmpeg não entregou um MP4 completo (código "+str(code)+"). "+" | ".join(errors))
        if progress:progress("Conferindo duração e finalizando MP4…")
        validate_export_media(Path(tmp_name),duration_seconds,events)
        # Same-directory hard link publishes the complete MP4 atomically and
        # refuses to replace a file created while the conversion ran.
        try:
            os.link(tmp_name, target)
        except FileExistsError:
            raise
        except OSError:
            # Filesystems without hard links (e.g. FAT) still support exclusive creation.
            created=False
            try:
                with target.open('xb') as destination_file, open(tmp_name,'rb') as source_file:
                    created=True
                    shutil.copyfileobj(source_file,destination_file)
                    destination_file.flush();os.fsync(destination_file.fileno())
            except Exception:
                if created:target.unlink(missing_ok=True)
                raise
        if diagnostics:diagnostics('MP4 finalizado e salvo; tamanho '+str(target.stat().st_size)+' bytes')
        if progress:
            progress("Convertido • 100%")
        return target
    except FileExistsError as exc:
        raise RecordingExportError("O arquivo de destino já existe; escolha outro nome") from exc
    except OSError as exc:
        raise RecordingExportError("Não foi possível gravar o MP4 no destino: "+type(exc).__name__) from exc
    finally:
        watchdog_done.set()
        if sdk_client:sdk_client.close()
        for descriptor in (input_read,input_write):
            if descriptor>=0:os.close(descriptor)
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        Path(tmp_name).unlink(missing_ok=True)


def export_bounds(start, end, marked_start=None, marked_end=None):
    """Marks belong to the day, independently of the selected recording file."""
    begin = marked_start if marked_start is not None else start
    finish = marked_end if marked_end is not None else end
    if (begin.tzinfo is not None or finish.tzinfo is not None or
            not 0 < (finish-begin).total_seconds() <= 86400):
        raise ValueError("Recorte inválido; escolha início e fim dentro de 24 horas")
    return begin, finish

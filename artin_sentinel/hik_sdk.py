"""Explicit opt-in local Hikvision SDK routes and bounded subprocess client."""
from datetime import datetime
import ipaddress
import json
import os
from pathlib import Path
import platform
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse,parse_qs,urlencode

def data_dir():
    from .paths import data_dir as app_data_dir
    return app_data_dir()
def settings(device):
    try:raw=json.loads(device['metadata_json'] or '{}').get('hik_sdk',{})
    except (ValueError,KeyError,TypeError,IndexError):raw={}
    if not isinstance(raw,dict):raw={}
    try:port=int(raw.get('port') or 8000)
    except (ValueError,TypeError):port=8000;raw={}
    if not 1<=port<=65535:port=8000;raw={}
    channels=raw.get('channels',{})
    if not isinstance(channels,dict):channels={}
    return {'enabled':raw.get('enabled') is True,'live':raw.get('live') is True,
            'port':port,'channels':channels}

def sdk_channel(device,channel):
    config=settings(device)
    if not config['enabled']:return None
    try:
        value=config['channels'].get(str(int(channel)))
        return int(value) if value is not None and 1<=int(value)<=256 else None
    except (TypeError,ValueError):return None

def route(host,port,channel,start=None,end=None,stream='main'):
    query={'stream':stream}
    if start is not None:query.update(start=start.isoformat(timespec='seconds'),end=end.isoformat(timespec='seconds'))
    authority=f'[{host}]' if ':' in host else host
    result=f'hik-sdk://{authority}:{int(port)}/{int(channel)}?{urlencode(query)}'
    parse_route(result)
    return result

def parse_route(url):
    p=urlparse(str(url));q=parse_qs(p.query,keep_blank_values=True,strict_parsing=True)
    if (p.scheme!='hik-sdk' or p.username is not None or p.password is not None or p.fragment
        or set(q) not in ({'stream'},{'stream','start','end'}) or any(len(v)!=1 for v in q.values())):
        raise ValueError('Rota SDK Hikvision inválida.')
    ipaddress.ip_address(p.hostname)
    channel=int(p.path.removeprefix('/'))
    if p.port is None or not 1<=p.port<=65535 or not 1<=channel<=256 or q['stream'][0] not in ('main','sub'):
        raise ValueError('Canal/porta/perfil SDK inválido.')
    result={'host':p.hostname,'port':p.port,'channel':channel,'stream':q['stream'][0]}
    if 'start' in q:
        begin,end=(datetime.fromisoformat(q[k][0]) for k in ('start','end'))
        if begin.tzinfo or end.tzinfo or not 0<(end-begin).total_seconds()<=86400:raise ValueError('Período SDK inválido.')
        result.update(start=begin.isoformat(),end=end.isoformat())
    return result

def live_choice(device,channel,forced=None):
    config=settings(device);number=sdk_channel(device,channel)
    if not config['live'] or number is None:return None
    # Auto stays on field-validated Main. Sub is only attempted when explicitly selected.
    stream='sub' if forced=='sub' else 'main'
    return stream,route(device['ip'],config['port'],number,stream=stream),'',''

def runtime_dir():
    try:
        root=Path(json.loads((data_dir()/'hik-sdk-runtime.json').read_text())['library_dir'])
    except (OSError,ValueError,KeyError,TypeError):raise ValueError('Importe o SDK Hikvision em Equipamentos → SDK Hikvision local.') from None
    if not (root/'libhcnetsdk.so').is_file():raise ValueError('Runtime Hikvision não encontrado; importe novamente o SDK.')
    return root

def import_runtime(directory):
    source=Path(directory).expanduser().resolve()
    matches=[];count=0
    for folder,dirs,files in os.walk(source,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink()]
        if len(Path(folder).relative_to(source).parts)>8:dirs[:]=[]
        count+=len(files)
        if count>5000:raise ValueError('Pasta muito ampla; selecione a pasta do SDK extraído.')
        if 'libhcnetsdk.so' in files:matches.append(Path(folder)/'libhcnetsdk.so')
    if len(matches)!=1:raise ValueError('Selecione uma pasta contendo uma única libhcnetsdk.so.')
    library=matches[0]
    if library.is_symlink():raise ValueError('Biblioteca principal não pode ser link simbólico.')
    with library.open("rb") as stream:header=stream.read(20)
    if len(header)<20 or header[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(header[18:20],'little')!=62:
        raise ValueError('SDK exige ELF Linux x86_64.')
    root=library.parent;total=0
    for p in root.rglob('*'):
        if p.is_symlink() and not p.resolve().is_relative_to(root):raise ValueError('Link fora da pasta do SDK recusado.')
        if p.is_file():total+=p.stat().st_size
        if total>512*1024*1024:raise ValueError('Runtime excede 512 MiB.')
    vendor=data_dir()/'vendor/hikvision-hcnetsdk'
    if vendor.resolve().is_relative_to(root):raise ValueError('Selecione a pasta original do SDK, fora do destino persistente.')
    vendor.mkdir(parents=True,exist_ok=True)
    target=Path(tempfile.mkdtemp(prefix='runtime-',dir=vendor))/'lib'
    try:shutil.copytree(root,target,symlinks=False)
    except Exception:
        shutil.rmtree(target.parent,ignore_errors=True);raise
    config=data_dir()/'hik-sdk-runtime.json'
    fd,pending=tempfile.mkstemp(prefix='.hik-sdk-',dir=config.parent)
    with os.fdopen(fd,'w') as stream:json.dump({'version':1,'library_dir':str(target)},stream)
    os.replace(pending,config)
    return str(target)

class Client:
    def __init__(self,options,username,password,media_fd=None):
        for value in (username,password):
            if not value or '\0' in value or len(value.encode())>=64:raise ValueError('Credenciais SDK exigem de 1 a 63 bytes UTF-8.')
        if platform.machine().lower()!='x86_64':raise ValueError('SDK Hikvision validado somente em Linux x86_64.')
        root=runtime_dir()
        self.events=[];self.buffer=bytearray();self.event_fd=self.cancel_fd=-1;self.process=None
        er,ew=os.pipe();cr,cw=os.pipe()
        env=os.environ.copy();env['LD_LIBRARY_PATH']=str(root)+os.pathsep+str(root/'HCNetSDKCom')+os.pathsep+env.get('LD_LIBRARY_PATH','')
        request=dict(options,username=username,password=password,library=str(root/'libhcnetsdk.so'),cancel_fd=cr)
        if media_fd is not None:request['media_fd']=media_fd
        try:
            self.process=subprocess.Popen([sys.executable,'-I','-S',str(Path(__file__).with_name('hik_sdk_worker.py')),str(ew)],
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                pass_fds=(ew,cr)+((media_fd,) if media_fd is not None else ()),env=env,cwd=root,start_new_session=True)
            self.event_fd,self.cancel_fd=er,cw;er=cw=-1
            os.set_blocking(self.event_fd,False)
            self.process.stdin.write(json.dumps(request).encode());self.process.stdin.close()
        except Exception:
            self.close();raise ValueError('Não foi possível iniciar o SDK isolado.') from None
        finally:
            for fd in (er,ew,cr,cw):
                if fd>=0:os.close(fd)
    def poll_events(self):
        if self.event_fd<0:return []
        while True:
            try:chunk=os.read(self.event_fd,65536)
            except BlockingIOError:break
            if not chunk:break
            self.buffer.extend(chunk)
            if len(self.buffer)>262144:raise ValueError('Resposta SDK excessiva.')
        result=[]
        while b'\n' in self.buffer:
            raw,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
            event=json.loads(raw);result.append(event)
        self.events.extend(result);self.events=self.events[-64:]
        return result
    def request_stop(self):
        fd=self.cancel_fd;self.cancel_fd=-1
        if fd>=0:os.close(fd)
    def close(self):
        self.request_stop()
        if self.process:
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                for sig in (signal.SIGTERM,signal.SIGKILL):
                    try:os.killpg(self.process.pid,sig)
                    except ProcessLookupError:pass
                    try:self.process.wait(timeout=.5);break
                    except subprocess.TimeoutExpired:pass
        if self.event_fd>=0:
            self.poll_events();os.close(self.event_fd);self.event_fd=-1

def search_recordings(device,username,password,channels,start,end,*,cancel_event=None):
    from .recording_search import Recording,SearchResult,RecordingSearchError
    if cancel_event is not None and cancel_event.is_set():raise RecordingSearchError('Pesquisa cancelada.')
    if not channels or len(channels)>4 or end<=start or (end-start).total_seconds()>86400:raise RecordingSearchError('Selecione até quatro canais e período de até 24 horas.')
    records=[];warnings=[];partial=False
    config=settings(device)
    for channel in channels:
        if cancel_event is not None and cancel_event.is_set():raise RecordingSearchError('Pesquisa cancelada.')
        native=sdk_channel(device,channel)
        if native is None:raise RecordingSearchError(f'CAM {channel}: mapeie o canal em SDK Hikvision local.')
        options=dict(host=device['ip'],port=config['port'],channel=native,action='search',start=start.isoformat(),end=end.isoformat())
        client=Client(options,username,password)
        try:
            deadline=time.monotonic()+30;answer=None
            while time.monotonic()<deadline:
                if cancel_event is not None and cancel_event.is_set():raise RecordingSearchError('Pesquisa cancelada.')
                for event in client.poll_events():
                    if event['stage']=='search_result':answer=event['result']
                    if event['stage'] in ('error','login_failed'):raise RecordingSearchError('SDK Hikvision: '+event['stage']+' • código '+str(event.get('code','—')))
                if client.process.poll() is not None:
                    for event in client.poll_events():
                        if event['stage']=='search_result':answer=event['result']
                    break
                time.sleep(.03)
            if answer is None:raise RecordingSearchError('Consulta SDK sem resultado; processo encerrado ou prazo atingido.')
            if answer['status'] not in ('completed','no_files_in_requested_day','result_limit','search_time_limit'):
                raise RecordingSearchError('Busca SDK não concluída • '+answer['status']+' • '+str(answer.get('sdk_error','—')))
            partial|=answer.get('partial',False)
            if not answer.get('search_close_ok',True):warnings.append('SDK não confirmou o encerramento da busca.')
            for row in answer['files']:
                if not row['start'] or not row['end']:partial=True;continue
                begin,finish=(datetime.fromisoformat(row[k]) for k in ('start','end'))
                if finish<=begin or begin>=end or finish<=start:continue
                records.append(Recording(channel,begin.strftime('%Y-%m-%d %H:%M:%S'),finish.strftime('%Y-%m-%d %H:%M:%S'),
                    'SDK • gravação',row['size_bytes_reported'],route(device['ip'],config['port'],native,begin,finish)))
        finally:client.close()
    return SearchResult(tuple(records),partial,0,tuple(warnings),('Hikvision SDK local • horários do DVR • reprodução em validação',))

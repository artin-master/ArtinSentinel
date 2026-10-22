"""Managed original P2P module under Wine. Credentials stay in NetSDK IPC.

Only six operator-provided, hash-verified DLLs are imported. One disposable
Wine process per serial/remote port is shared by its consumers, with graceful
stop-file cancellation before bounded termination. No GUI APIs are used here.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import zipfile

ASSETS=Path(__file__).with_name('resources')/'cloud_wine'


def default_root():
    return Path.home()/'.local/share/artin-sentinel/vendor/intelbras-cloud-wine'


def default_prefix():
    previous=Path.home()/'.local/share/artin-sentinel/wine-cloud-teste'
    return previous if previous.is_dir() else Path.home()/'.local/share/artin-sentinel/wine-cloud'


def _manifest():
    return json.loads((ASSETS/'baseline.json').read_text())['files']


def _fingerprint():
    digest=hashlib.sha256()
    for name in ('Runner.cs','Loader.cs','Initialization.cs','Tunnel.cs','baseline.json'):
        digest.update((ASSETS/name).read_bytes())
    return digest.hexdigest()


def extract_verified(archive,destination):
    values={}
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist()
        for item in _manifest():
            matches=[v for v in entries if v.filename=='SIMNext/SIM Next/'+item['name']]
            if len(matches)!=1 or matches[0].file_size!=item['bytes']:
                raise ValueError('Biblioteca ausente ou diferente da base: '+item['name'])
            data=z.read(matches[0])
            if hashlib.sha256(data).hexdigest()!=item['sha256']:
                raise ValueError('Hash divergente: '+item['name'])
            values[item['name']]=data
    destination=Path(destination)
    destination.mkdir(mode=0o700)
    for name,data in values.items():
        (destination/name).write_bytes(data)


def wine_environment(prefix):
    env=dict(os.environ)
    env['WINEPREFIX']=str(prefix)
    iconv=Path('/usr/x86_64-w64-mingw32/sys-root/mingw/bin/iconv.dll')
    if iconv.is_file():
        value='Z:'+str(iconv.parent).replace('/',chr(92))
        env['WINEPATH']=value+(';' + env['WINEPATH'] if env.get('WINEPATH') else '')
    return env


def _winpath(path,env):
    r=subprocess.run(['winepath','-w',str(path)],env=env,capture_output=True,text=True,timeout=15)
    if r.returncode or not r.stdout.strip():
        raise ValueError('Wine não conseguiu preparar os caminhos locais.')
    return r.stdout.strip()


def _read(path):
    try:
        result=json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return result if isinstance(result,dict) else {}
    except (OSError,ValueError):
        return {}


def _stop_process(process):
    if process.poll() is not None:
        return
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait(timeout=2)


class _Tunnel:
    def __init__(self,manager,serial,remote):
        self.manager=manager
        self.refs=0
        self.key=(serial,remote)
        self.idle_deadline=None
        self.ready=threading.Event()
        self.done=threading.Event()
        self.stop_requested=threading.Event()
        self.report={}
        self.error='Ponte Wine não ficou pronta.'
        self.port=None
        self.work=tempfile.TemporaryDirectory(prefix='as-wine-session-')
        self.directory=Path(self.work.name)
        self.report_path=self.directory/'report.json'
        self.stop_path=self.directory/'stop'
        self.process=None
        try:
            factory=manager.command_factory
            if factory:
                argv=factory(self.report_path,self.stop_path,remote)
                request=('synthetic\n'+serial+'\n'+str(remote)+'\n').encode()
                env=None
            else:
                env=wine_environment(manager.prefix)
                argv=[shutil.which('wine'),str(manager.root/'Bridge.exe'),
                      _winpath(self.report_path,env),_winpath(self.stop_path,env)]
                request=(_winpath(manager.root/'originals',env)+'\n'+serial+'\n'+str(remote)+'\n').encode('utf-8')
            self.process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,cwd=self.directory,env=env,start_new_session=True)
            try:
                self.process.stdin.write(request);self.process.stdin.close()
            except BrokenPipeError:
                pass
            self.thread=threading.Thread(target=self._monitor,name='as-cloud-wine',daemon=True)
            self.thread.start()
        except BaseException:
            if self.process is not None:_stop_process(self.process)
            self.work.cleanup()
            raise

    def _monitor(self):
        deadline=time.monotonic()+self.manager.startup_timeout
        stop_deadline=None
        try:
            while self.process.poll() is None:
                self.report=_read(self.report_path) or self.report
                value=self.report.get('local_port')
                if self.report.get('phase')=='tunnel_hold' and isinstance(value,int) and 1<=value<=65535:
                    self.port=value
                    self.ready.set()
                self.manager._expire_idle(self)
                if not self.ready.is_set() and time.monotonic()>=deadline:
                    self.error='A abertura da ponte Wine excedeu o prazo. Confira Wine/Mono e o DVR.'
                    self.stop_requested.set()
                if self.stop_requested.is_set():
                    self.stop_path.touch(exist_ok=True)
                    if stop_deadline is None:stop_deadline=time.monotonic()+self.manager.close_timeout
                    if time.monotonic()>=stop_deadline:
                        _stop_process(self.process)
                        break
                time.sleep(.05)
            self.process.wait(timeout=2)
            self.report=_read(self.report_path) or self.report
            if not self.ready.is_set():
                result=self.report.get('result','worker_no_report')
                missing=self.report.get('missing') or []
                if missing:
                    self.error='Dependências ausentes na ponte Wine: '+', '.join(str(v) for v in missing if re.fullmatch(r'[A-Za-z0-9_.-]+',str(v)))
                elif result in {'native_setup_failed','constructor_failed_cleanup_unconfirmed'}:
                    self.error='O módulo original não inicializou no Wine/Mono. Consulte o diagnóstico da ponte.'
        finally:
            if self.process.poll() is None:_stop_process(self.process)
            self.report['child_exit_code']=self.process.returncode
            self.report['child_terminated']=self.process.poll() is not None
            try:
                self.manager.root.mkdir(parents=True,exist_ok=True)
                diagnostic=self.manager.root/'last_session.json'
                pending=self.manager.root/('last_session.'+str(self.process.pid)+'.pending')
                pending.write_text(json.dumps(self.report,ensure_ascii=False,indent=2))
                pending.chmod(0o600)
                os.replace(pending,diagnostic)
            except OSError:
                pass
            self.done.set()
            self.ready.set()  # wakes unsuccessful waiters too
            self.manager._tunnel_finished(self)
            self.work.cleanup()

    def alive(self):
        return self.port is not None and not self.done.is_set() and self.process.poll() is None

    def close(self):
        self.stop_requested.set()
        self.done.wait(self.manager.close_timeout+4)
        if not self.done.is_set():
            _stop_process(self.process)
            self.done.wait(2)


class WineLease:
    def __init__(self,manager,key,entry):
        self.manager,self.key,self.entry=manager,key,entry
        self.port=entry.port
        self._lock=threading.Lock()
        self._released=False

    def release(self):
        with self._lock:
            if self._released:return
            self._released=True
        self.manager._release(self.key,self.entry)

    def __enter__(self):return self
    def __exit__(self,*_):self.release()


class WineTunnelManager:
    def __init__(self,*,root=None,prefix=None,command_factory=None,startup_timeout=50,close_timeout=3,idle_timeout=180):
        self.root=Path(root or default_root())
        self.prefix=Path(prefix or default_prefix())
        self.command_factory=command_factory
        self.startup_timeout=startup_timeout
        self.close_timeout=close_timeout
        self.idle_timeout=float(idle_timeout)
        if not math.isfinite(self.idle_timeout) or self.idle_timeout<0:
            raise ValueError('Prazo de inatividade da ponte inválido.')
        self.entries={}
        self.lock=threading.RLock()
        self.setup_lock=threading.RLock()
        self.closed=False

    def installed(self):
        stamp=_read(self.root/'installed.json')
        if stamp.get('source_fingerprint')!=_fingerprint() or not (self.root/'Bridge.exe').is_file():
            return False
        return all((self.root/'originals'/v['name']).is_file() and
                   hashlib.sha256((self.root/'originals'/v['name']).read_bytes()).hexdigest()==v['sha256']
                   for v in _manifest())

    def prepare(self,archive=None,*,cancel_event=None,progress=None):
        tell=progress or (lambda _:None)
        with self.setup_lock:
            if archive is None and self.installed():return
            with self.lock:
                if self.closed:raise ValueError('O Sentinel está sendo encerrado.')
                if self.entries:raise ValueError('Feche os canais Cloud antes de preparar novamente a ponte.')
            if not shutil.which('wine') or not shutil.which('winepath'):
                raise ValueError('Wine não encontrado. Execute preparar-cloud.sh do instalador.')
            if not self.prefix.is_dir():
                raise ValueError('Ambiente Wine ausente. Execute preparar-cloud.sh do instalador.')
            if cancel_event is not None and cancel_event.is_set():raise ValueError('Preparação cancelada.')
            self.root.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='as-wine-setup-',dir=self.root.parent) as temp:
                stage=Path(temp)
                tell('Conferindo bibliotecas Intelbras…')
                if archive:
                    extract_verified(Path(archive),stage/'originals')
                elif (self.root/'originals').is_dir():
                    shutil.copytree(self.root/'originals',stage/'originals')
                    for item in _manifest():
                        if hashlib.sha256((stage/'originals'/item['name']).read_bytes()).hexdigest()!=item['sha256']:
                            raise ValueError('Bibliotecas Wine diferentes da base verificada.')
                else:raise ValueError('Selecione SIMNextWINInstall.zip para preparar as bibliotecas uma vez.')
                for name in ('Runner.cs','Loader.cs','Initialization.cs','Tunnel.cs'):
                    shutil.copyfile(ASSETS/name,stage/name)
                tell('Compilando a ponte Wine x64…')
                command=[shutil.which('wine'),r'C:\windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe',
                    '/nologo','/target:exe','/platform:x64','/out:Bridge.exe',
                    'Runner.cs','Loader.cs','Initialization.cs','Tunnel.cs']
                compiler=subprocess.Popen(command,cwd=stage,env=wine_environment(self.prefix),
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                deadline=time.monotonic()+60
                try:
                    while compiler.poll() is None:
                        if cancel_event is not None and cancel_event.is_set():raise ValueError('Preparação cancelada.')
                        if time.monotonic()>deadline:raise ValueError('A compilação da ponte Wine excedeu o prazo.')
                        time.sleep(.05)
                finally:
                    if compiler.poll() is None:_stop_process(compiler)
                if compiler.returncode or not (stage/'Bridge.exe').is_file():
                    raise ValueError('A ponte não compilou. Confira Wine Mono com preparar-cloud.sh; detalhes do fornecedor não foram gravados.')
                if cancel_event is not None and cancel_event.is_set():raise ValueError('Preparação cancelada.')
                with self.lock:
                    if self.closed:raise ValueError('O Sentinel está sendo encerrado.')
                (stage/'installed.json').write_text(json.dumps({'source_fingerprint':_fingerprint()}))
                self.root.mkdir(exist_ok=True)
                # All users of this manager are excluded by setup_lock during preparation.
                for item in ('Bridge.exe','installed.json'):
                    os.replace(stage/item,self.root/item)
                previous=self.root/'originals'
                if previous.exists():shutil.rmtree(previous)
                os.replace(stage/'originals',previous)
                tell('Ponte Wine preparada.')

    def acquire(self,serial,remote=37777,*,cancel_event=None,progress=None):
        serial=str(serial).strip().upper()
        if not re.fullmatch(r'[A-Z0-9_-]{4,47}',serial) or not 1<=int(remote)<=65535:
            raise ValueError('Serial ou porta do DVR inválidos.')
        if cancel_event is not None and cancel_event.is_set():raise ValueError('Conexão cancelada.')
        key=(serial,int(remote))
        while True:
            closing=None
            with self.setup_lock:
                if not self.command_factory:
                    self.prepare(cancel_event=cancel_event,progress=progress)
                with self.lock:
                    if self.closed:raise ValueError('O Sentinel está sendo encerrado.')
                    entry=self.entries.get(key)
                    if entry is not None and not entry.done.is_set() and (entry.stop_requested.is_set() or entry.process.poll() is not None):
                        closing=entry
                    else:
                        reused=entry is not None and entry.alive()
                        if entry is None or entry.done.is_set():
                            entry=_Tunnel(self,serial,int(remote));self.entries[key]=entry
                        entry.refs+=1
                        entry.idle_deadline=None
            if closing is None:break
            # Never start a replacement while the previous native helper is closing.
            while not closing.done.wait(.05):
                if cancel_event is not None and cancel_event.is_set():raise ValueError('Conexão cancelada.')
                if self.closed:raise ValueError('O Sentinel está sendo encerrado.')
            if cancel_event is not None and cancel_event.is_set():raise ValueError('Conexão cancelada.')
        last=None
        try:
            shown=None
            while not entry.ready.wait(.05):
                if cancel_event is not None and cancel_event.is_set():raise ValueError('Conexão cancelada.')
                phase=entry.report.get('phase')
                if progress and phase!=last:
                    last=phase
                    message='Abrindo túnel pelo serial…' if phase in {'add_sdk_port_started','tunnel_status'} else 'Inicializando a ponte Wine…'
                    if message!=shown:progress(message);shown=message
            if cancel_event is not None and cancel_event.is_set():raise ValueError('Conexão cancelada.')
            if not entry.alive():raise ValueError(entry.error)
            if progress:progress('Reutilizando túnel Wine ativo…' if reused else 'Túnel Wine pronto…')
            return WineLease(self,key,entry)
        except BaseException:
            self._release(key,entry)
            raise

    def _release(self,key,entry):
        close=False
        with self.lock:
            entry.refs=max(0,entry.refs-1)
            if entry.refs==0:
                if not self.closed and self.idle_timeout>0 and entry.alive() and not entry.stop_requested.is_set():
                    entry.idle_deadline=time.monotonic()+self.idle_timeout
                else:
                    entry.idle_deadline=None
                    entry.stop_requested.set()
                    close=True
        if close:
            entry.close()
            self._tunnel_finished(entry)

    def _expire_idle(self,entry):
        # Called by the existing tunnel monitor; serialized with acquire/release.
        with self.lock:
            if entry.refs==0 and entry.idle_deadline is not None and time.monotonic()>=entry.idle_deadline:
                entry.idle_deadline=None
                entry.stop_requested.set()

    def _tunnel_finished(self,entry):
        with self.lock:
            if entry.done.is_set() and entry.refs==0 and self.entries.get(entry.key) is entry:
                self.entries.pop(entry.key,None)

    def shutdown(self):
        with self.lock:
            self.closed=True
            entries=list(self.entries.values());self.entries.clear()
        for entry in entries:entry.stop_requested.set()
        for entry in entries:entry.close()


_singleton=None
_singleton_lock=threading.Lock()


def wine_manager():
    global _singleton
    with _singleton_lock:
        if _singleton is None:_singleton=WineTunnelManager()
        return _singleton


def shutdown_wine():
    if _singleton is not None:_singleton.shutdown()

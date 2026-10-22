"""Extensible read-only component inventory. Native loads run in isolated children."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

class ComponentRegistry:
    def __init__(self):self.providers={}
    def register(self,key,name,inspect):self.providers[key]=(name,inspect)
    def inspect(self):
        rows=[]
        for key,(name,check) in self.providers.items():
            try:result=check()
            except Exception:result={'state':'Não verificado','detail':'Verificação não concluída; consulte o componente.'}
            rows.append(dict(result,key=key,name=name))
        return rows

def executable(name):
    path=shutil.which(name)
    if not path:return dict(state='Ausente',version='—',detail='Instale pelo gerenciador de pacotes da distribuição.')
    try:
        r=subprocess.run([path,'--version' if name=='wine' else '-version'],capture_output=True,text=True,timeout=6)
        version=(r.stdout or r.stderr).splitlines()[0][:180]
    except (OSError,subprocess.TimeoutExpired):return dict(state='Encontrado',version='—',detail='Executável presente; execução não confirmada.')
    return dict(state='Disponível',version=version,detail='Executável respondeu; isso não valida conexão com DVR.')

def native_load(path):
    path=Path(path)
    if not path.is_file():return dict(state='Ausente',version='—',detail='Runtime ainda não importado.')
    env=dict(os.environ);env['LD_LIBRARY_PATH']=str(path.parent)+os.pathsep+env.get('LD_LIBRARY_PATH','')
    code="""import ctypes,sys,json
lib=ctypes.CDLL(sys.argv[1],mode=ctypes.RTLD_GLOBAL)
symbol='NET_DVR_GetSDKBuildVersion' if 'hcnetsdk' in sys.argv[1] else 'CLIENT_GetSDKVersion'
version='Não anunciada'
if hasattr(lib,symbol):
 f=getattr(lib,symbol);f.argtypes=[];f.restype=ctypes.c_uint32
 version=hex(f())
print(json.dumps({'version':version}))
"""
    try:
        r=subprocess.run([sys.executable,'-I','-S','-c',code,str(path)],capture_output=True,text=True,timeout=10,env=env)
        return dict(state='Carregamento OK' if r.returncode==0 else 'Falha no carregamento',version=__import__('json').loads(r.stdout).get('version','—') if r.returncode==0 else '—',detail='Biblioteca carregada em processo isolado; sem login ou conexão.' if r.returncode==0 else 'Biblioteca presente; dependência ausente ou runtime incompatível. Nenhum DVR foi acessado.')
    except (OSError,subprocess.TimeoutExpired):return dict(state='Não verificado',version='—',detail='Prazo de carregamento excedido ou processo indisponível.')

def default_registry():
    reg=ComponentRegistry()
    for name in ('ffmpeg','ffprobe','ffplay','wine'):reg.register(name,name,lambda n=name:executable(n))
    def codecs():
        ff=shutil.which('ffmpeg')
        if not ff:return dict(state='Ausente',detail='FFmpeg não encontrado.')
        r=subprocess.run([ff,'-hide_banner','-decoders'],capture_output=True,text=True,timeout=8)
        names={line.split()[1] for line in r.stdout.splitlines() if len(line.split())>2}
        return dict(state='Verificado',version='FFmpeg',detail=' · '.join(f"{label}: {'disponível' if name in names else 'ausente'}" for name,label in [('h264','H.264'),('hevc','H.265'),('aac','AAC'),('pcm_mulaw','G.711u'),('pcm_alaw','G.711a')]))
    reg.register('codecs','Decodificadores de vídeo e áudio',codecs)
    from .intelbras_netsdk import vendor_install_directory
    reg.register('intelbras-sdk','Intelbras NetSDK',lambda:native_load(vendor_install_directory()/'libdhnetsdk.so'))
    def hik():
        from .hik_sdk import runtime_dir
        try:return native_load(runtime_dir()/'libhcnetsdk.so')
        except ValueError:return dict(state='Ausente',version='—',detail='Importe a pasta do SDK oficial Linux x86_64.')
    reg.register('hikvision-sdk','Hikvision HCNetSDK',hik)
    def bridge():
        from .intelbras_wine import default_prefix
        root=default_prefix()
        return dict(state='Prefixo presente' if root.is_dir() else 'Não preparado',version='—',detail='Presença local não confirma túnel Cloud ativo. Consulte as sessões abaixo.')
    reg.register('intelbras-bridge','Ponte Intelbras Cloud / Wine',bridge)
    return reg

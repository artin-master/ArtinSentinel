"""Conservative estimates for the currently measured stream mix, not hardware guarantees."""
from pathlib import Path
import os
import time
from .performance import process_sample


def estimate_capacity(samples):
    missing = dict(measured=0,recommended=None,estimated=False,note='Medição insuficiente ou perfil alterado; repita com câmeras estáveis.')
    if len(samples)<8 or any(not s['stable'] for s in samples):return missing
    counts={s['channels'] for s in samples}
    if len(counts)!=1 or not next(iter(counts)):return missing
    n=next(iter(counts));cpu=max(s['cpu'] for s in samples)
    system=max(s['system_cpu'] for s in samples);fps=sum(s['fps_ratio'] for s in samples)/len(samples)
    available=min(s['available_mb'] for s in samples);rss=max(s['rss_mb'] for s in samples)
    if fps<.8:
        return dict(measured=n,recommended=None,estimated=False,note='Recebimento de quadros abaixo do alvo; origem/rede também podem limitar. Não é possível estimar a capacidade do PC.')
    # No more than 2× the tested count. Reserve 25% CPU and at least 1 GiB RAM.
    cpu_extra=max(0,75-system)/max(cpu/n,1)
    ram_extra=max(0,available-1024)/max(rss/n,64)
    capacity=max(1,min(n*2,int(n+min(cpu_extra,ram_extra))))
    if system>85 or available<512:capacity=max(1,n-1)
    return dict(measured=n,recommended=capacity,estimated=True,note='Estimativa conservadora para o mesmo perfil/mistura de streams. Resolução, codec, Main/Sub, FPS e outros aplicativos mudam o resultado; valide ao adicionar câmeras.')


class PressureWarning:
    def __init__(self):self.streak=0;self.last=-1e9
    def update(self,sample,now=None):
        now=time.monotonic() if now is None else now
        limit=sample.get('recommended')
        delivery=bool(limit is not None and sample['channels']>limit and sample['fps_ratio']<.8)
        pressure=sample['channels']>0 and sample['stable'] and (sample['system_cpu']>=85 or sample['available_mb']<512 or delivery)
        self.streak=self.streak+1 if pressure else 0
        if self.streak>=3 and now-self.last>=120:
            self.last=now;self.streak=0;return True
        return False


def _system():
    values=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return sum(values),values[3]+values[4],int(memory['MemAvailable'].split()[0])/1024


def _pids():
    # All descendants include FFmpeg, SDK workers, Wine and audio; no command lines recorded.
    relations={}
    for item in Path('/proc').iterdir():
        if not item.name.isdecimal():continue
        try:relations[int(item.name)]=int((item/'stat').read_text().rsplit(') ',1)[1].split()[1])
        except (OSError,ValueError,IndexError):pass
    selected={os.getpid()}
    for _ in range(12):
        added={pid for pid,parent in relations.items() if parent in selected}
        if added<=selected:break
        selected.update(added)
    return selected


class PCSampler:
    def __init__(self):self.previous=None;self.frames={};self.signature=None
    def sample(self,sessions):
        sessions=list(sessions);signature=tuple(sorted((id(s),s.active_profile,s.fps,getattr(s,'reconnects',0)) for s in sessions))
        frames={id(s):s.frame_count for s in sessions};now=time.monotonic()
        try:total,idle,available=_system()
        except (OSError,ValueError,KeyError):return None
        process=process_sample(_pids());cores=max(1,len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else os.cpu_count() or 1)
        stable=self.signature==signature and bool(sessions)
        cpu=system=ratio=0.0
        if self.previous:
            elapsed=max(.001,now-self.previous[0]);delta=total-self.previous[1]
            system=max(0,min(100,100*(1-(idle-self.previous[2])/delta))) if delta>0 else 0
            cpu=max(0,min(100,100*(process[1]-self.previous[3])/elapsed/cores))
            ratio=min(1,sum(max(0,frames[k]-self.frames.get(k,frames[k])) for k in frames)/max(1,elapsed*sum(s.fps for s in sessions)))
        self.previous=(now,total,idle,process[1]);self.frames=frames;self.signature=signature
        return dict(channels=len(sessions),cpu=round(cpu,1),system_cpu=round(system,1),available_mb=round(available),rss_mb=round(process[2]),fps_ratio=round(ratio,3),stable=stable,profiles=sorted(set('Sub' if 'sub' in s.active_profile.lower() else 'Main' if 'main' in s.active_profile.lower() else 'perfil não informado' for s in sessions)))

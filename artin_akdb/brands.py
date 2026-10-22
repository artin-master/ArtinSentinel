"""Local manufacturer presentation preferences, separate from official knowledge.

Additive tables let older Artin applications continue reading the same AKDB.
Saving a color/name does not homologate a model or enqueue evidence for upload.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3
from uuid import uuid4
import hashlib
from .store import default_store_path, SharedAkdbStore

NEUTRAL = '#AABBC8'

def normalize(value):
    return ' '.join(re.sub(r'[^\w]+',' ',str(value or '').casefold()).split())

@dataclass(frozen=True)
class Manufacturer:
    id: str
    name: str
    color: str = NEUTRAL
    aliases: tuple[str,...] = ()

DEFAULTS = tuple(Manufacturer('artin.manufacturer.'+key,name,color,aliases) for key,name,color,aliases in (
    ('intelbras','Intelbras','#55D996',()),
    ('positivo','Positivo','#64A8FF',('PositivoSEG',)),
    ('hikvision','Hikvision','#FF8585',()),
    ('hilook','HiLook','#FF9B9B',()),
    ('jfl','JFL','#E6CF69',()),
    ('haiz','Haiz','#FFAB66',()),
    ('aiktec','AikTec','#80DEEA',()),
    ('aitek','Aitek','#80DEEA',()),
    ('it-blue','IT-Blue','#AABBC8',('IT Blue',)),
))

def _validate(profile):
    if not re.fullmatch(r'artin\.manufacturer\.[a-z0-9-]{1,64}',profile.id):
        raise ValueError('Identificador de fabricante inválido.')
    if not profile.name.strip() or len(profile.name)>80 or any(ord(c)<32 for c in profile.name):
        raise ValueError('Informe um nome de fabricante de até 80 caracteres.')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',profile.color):
        raise ValueError('Escolha uma cor válida na paleta.')
    if len(profile.aliases)>30 or any(not a.strip() or len(a)>80 or any(ord(c)<32 for c in a) for a in profile.aliases):
        raise ValueError('Use até 30 nomes alternativos de até 80 caracteres.')
    # A very dark badge would be unreadable on the current dark workspace.
    rgb=[int(profile.color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4 for x in rgb]
    if sum(x*w for x,w in zip(linear,(.2126,.7152,.0722)))<.075:
        raise ValueError('Escolha uma cor mais clara para manter a marca legível no fundo escuro.')

class BrandRegistry:
    def __init__(self,path=None):
        self.path=Path(path) if path else default_store_path()
        self.profiles={p.id:p for p in DEFAULTS}
        from .catalog import CORE_RECORDS
        known={normalize(p.name) for p in self.profiles.values()}
        for record in CORE_RECORDS:
            if record.manufacturer and normalize(record.manufacturer) not in known:
                key=hashlib.sha256(normalize(record.manufacturer).encode()).hexdigest()[:20]
                p=Manufacturer('artin.manufacturer.'+key,record.manufacturer)
                self.profiles[p.id]=p;known.add(normalize(p.name))
        self.warning=''
        if self.path.is_file():
            try:
                with sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5) as c:
                    exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='manufacturer_preferences'").fetchone()
                    rows=c.execute('SELECT payload_json FROM manufacturer_preferences LIMIT 1000').fetchall() if exists else []
                for (raw,) in rows:
                    data=json.loads(raw);data['aliases']=tuple(data.get('aliases',()))
                    profile=Manufacturer(**data);_validate(profile)
                    candidate=dict(self.profiles);candidate[profile.id]=profile
                    self._index(candidate)  # invalid local rows cannot create ambiguous aliases
                    self.profiles=candidate
            except (sqlite3.Error,ValueError,TypeError,KeyError,OSError):
                self.warning='Algumas preferências de fabricantes não puderam ser lidas; revise o cadastro.'
        self.index=self._index(self.profiles)

    @staticmethod
    def _index(profiles):
        index={}
        for profile in profiles.values():
            for value in (profile.name,*profile.aliases):
                key=normalize(value)
                if key in index and index[key]!=profile.id:
                    raise ValueError('Nome ou alias já pertence a outro fabricante: '+value)
                index[key]=profile.id
        return index

    def resolve(self,name):
        key=self.index.get(normalize(name))
        return self.profiles[key] if key else None

    def all(self): return sorted(self.profiles.values(),key=lambda p:p.name.casefold())

    def save(self,profile):
        _validate(profile)
        existing=self.profiles.get(profile.id)
        # Preserve former names so devices already registered still resolve.
        aliases=tuple(dict.fromkeys(a.strip() for a in (*profile.aliases,*((existing.name,*existing.aliases) if existing else ())) if normalize(a)!=normalize(profile.name)))
        profile=Manufacturer(profile.id,profile.name.strip(),profile.color.upper(),aliases)
        _validate(profile)
        with SharedAkdbStore(self.path) as store:
            c=store.conn
            c.execute('CREATE TABLE IF NOT EXISTS manufacturer_preferences(id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,updated_at TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS manufacturer_preference_history(id INTEGER PRIMARY KEY,manufacturer_id TEXT NOT NULL,previous_json TEXT NOT NULL,current_json TEXT NOT NULL,updated_at TEXT NOT NULL)')
            c.execute('BEGIN IMMEDIATE')
            try:
                current=BrandRegistry(self.path)
                candidate=dict(current.profiles);candidate[profile.id]=profile
                self._index(candidate)
                before=current.profiles.get(profile.id)
                raw=json.dumps(asdict(profile),ensure_ascii=False);now=datetime.now(timezone.utc).isoformat()
                c.execute('INSERT OR REPLACE INTO manufacturer_preferences VALUES(?,?,?)',(profile.id,raw,now))
                c.execute('INSERT INTO manufacturer_preference_history(manufacturer_id,previous_json,current_json,updated_at) VALUES(?,?,?,?)',(profile.id,json.dumps(asdict(before)) if before else '{}',raw,now))
                c.commit()
            except Exception:
                c.rollback();raise
        self.profiles=candidate;self.index=self._index(candidate)

    def new(self,name,color=NEUTRAL,aliases=()):
        return Manufacturer('artin.manufacturer.'+uuid4().hex,name,color,tuple(aliases))

_current=None
def current_registry(reload=False):
    global _current
    if reload or _current is None or _current.path!=default_store_path():
        _current=BrandRegistry()
    return _current

def canonical_manufacturer(name):
    profile=current_registry().resolve(name)
    return profile.name if profile else str(name or '')

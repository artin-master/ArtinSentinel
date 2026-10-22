"""Bounded SDK login reuse for playback and separate recording queries."""
import atexit
import hashlib
from pathlib import Path
import threading
import time


class PlaybackLease:
    def __init__(self, pool, key, client):
        self.pool, self.key, self.client = pool, key, client
        self.released = False
        self.lock = threading.Lock()
        self._events = []

    def __getattr__(self, name):
        return getattr(self.client, name)

    def close(self):
        with self.lock:
            if self.released:return
            self.released = True
        self._events = self.pool.release(self.key, self.client)

    def request_stop(self):
        with self.lock:
            if not self.released:self.client.request_stop()

    def poll_events(self):
        with self.lock:
            return [] if self.released else self.client.poll_events()

    @property
    def events(self):
        return self._events if self.released else self.client.events


class PlaybackSessionPool:
    def __init__(self, idle_seconds=45, max_idle=4):
        self.idle_seconds, self.max_idle = idle_seconds, max_idle
        self.condition = threading.Condition()
        self.entries = {}  # key -> (client, in_use, expiry timer)
        self.closed = False

    def acquire(self, port, serial, username, password, *, cancel_event, **options):
        from .intelbras_cloud import BridgeProcess, default_sdk_dir
        key = (port, serial, username, hashlib.sha256(password.encode()).digest(),
               str(Path(options.get('sdk_dir') or default_sdk_dir()).expanduser().resolve()),
               options.get('host','127.0.0.1'), options.get('login_mode',19),
               'record-query' if options.get('record_query') is not None else options['channel'])
        deadline = time.monotonic()+5
        with self.condition:
            while key in self.entries and self.entries[key][1]:
                if cancel_event.is_set() or self.closed:raise ValueError('Reprodução cancelada.')
                if time.monotonic()>=deadline:raise ValueError('A sessão anterior ainda está encerrando. Tente novamente.')
                self.condition.wait(.05)
            if cancel_event.is_set() or self.closed:raise ValueError('Reprodução cancelada.')
            existing = self.entries.pop(key, None)
            if existing and existing[2]:existing[2].cancel()
            self.entries[key] = (None, True, None)
        client = existing[0] if existing else None
        try:
            if client is not None and client.process.poll() is not None:
                client.close();client=None
            if client is None:
                client=BridgeProcess(port,serial,username,password,persistent=True,**options)
            elif options.get('record_query') is not None:
                client.resume_query(options['record_query'])
            else:
                client.resume_playback(options['media_fd'],channel=options['channel'],stream=options['stream'],
                                       playback_window=options['playback_window'],playback_speed=options['playback_speed'])
            with self.condition:
                if self.closed:raise ValueError('Sentinel encerrando.')
                self.entries[key]=(client,True,None)
            return PlaybackLease(self,key,client)
        except Exception:
            if client is not None:client.close()
            with self.condition:
                self.entries.pop(key,None);self.condition.notify_all()
            raise

    def release(self, key, client):
        client.request_stop()
        try:
            healthy=client.wait_idle(4)
        except (OSError,ValueError):
            healthy=False
        discard=[]
        with self.condition:
            events=list(client.events)
            if not healthy or self.closed:
                self.entries.pop(key,None);discard.append(client)
            else:
                timer=threading.Timer(self.idle_seconds,self.expire,args=(key,client))
                timer.daemon=True
                self.entries[key]=(client,False,timer)
                idle=[(k,v) for k,v in self.entries.items() if not v[1]]
                for old_key,(old_client,_,old_timer) in idle[:-self.max_idle]:
                    old_timer.cancel();self.entries.pop(old_key,None);discard.append(old_client)
                timer.start()
            self.condition.notify_all()
        for item in discard:item.close()
        return events

    def expire(self, key, client):
        with self.condition:
            entry=self.entries.get(key)
            if entry is None or entry[0] is not client or entry[1]:return
            self.entries.pop(key)
            if entry[2]:entry[2].cancel()
        client.close()

    def shutdown(self):
        with self.condition:
            self.closed=True
            entries=list(self.entries.values());self.entries.clear();self.condition.notify_all()
        for client,_,timer in entries:
            if timer:timer.cancel()
            if client:client.close()


_pool=PlaybackSessionPool()

def playback_pool():
    return _pool

def shutdown_playback_pool():
    _pool.shutdown()

atexit.register(shutdown_playback_pool)

"""Bounded timing evidence from the GUI thread; no camera identifiers or user data."""
from collections import deque
import time


class UiMetrics:
    def __init__(self):self.calls={};self.lags=deque(maxlen=600);self.expected=None
    def run(self,name,callback):
        begin=time.monotonic()
        try:return callback()
        finally:self.calls.setdefault(name,deque(maxlen=300)).append((time.monotonic(),(time.monotonic()-begin)*1000))
    def heartbeat(self):
        now=time.monotonic()
        if self.expected is not None:self.lags.append((now,max(0,(now-self.expected)*1000)))
        self.expected=now+.25
    def snapshot(self,*,since=0):
        def stats(values):
            values=sorted(value for when,value in values if when>=since)
            if not values:return dict(amostras=0)
            return dict(amostras=len(values),media_ms=round(sum(values)/len(values),2),max_ms=round(values[-1],2),p95_ms=round(values[min(len(values)-1,int(len(values)*.95))],2))
        return dict(atraso_event_loop=stats(self.lags),callbacks={name:stats(values) for name,values in self.calls.items()})

"""Read FFmpeg progress without inventing advancement from the requested speed."""
from collections import deque
import math
import time

class PlaybackClock:
    def __init__(self, speed, *, now=time.monotonic):
        self.speed=float(speed);self.now=now;self.position=0.0
        self.available=False;self.samples=deque(maxlen=12);self._rate=None
    def update(self,line):
        if not line.startswith('out_time_us='):return False
        try:value=int(line.split('=',1)[1])/1_000_000*self.speed
        except (ValueError,OverflowError):return True
        if not math.isfinite(value) or value<0:return True
        self.position=max(self.position,value);self.available=True
        moment=self.now();self.samples.append((moment,self.position))
        first=self.samples[0]
        if moment-first[0]>=1:self._rate=(self.position-first[1])/(moment-first[0])
        return True
    @property
    def rate(self):
        if self.samples and self.now()-self.samples[-1][0]>2.5:return 0.0
        return self._rate

PROGRESS_KEYS=frozenset(('frame','fps','stream_0_0_q','bitrate','total_size','out_time_us','out_time_ms','out_time','dup_frames','drop_frames','speed','progress'))

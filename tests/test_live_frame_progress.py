"""Frame boundaries survive slow but progressing decoder output."""
import threading

import pytest

from artin_sentinel import live


class ScheduledPipe:
    def __init__(self, chunks):
        self.now = 0.0
        self.chunks = list(chunks)

    def fileno(self):
        return 42

    def select(self, readers, writers, errors, timeout):
        if not self.chunks or self.chunks[0][0] <= self.now:
            return readers, [], []
        self.now += timeout
        return (readers if self.chunks[0][0] <= self.now else []), [], []

    def read(self, size):
        if not self.chunks:
            return b""
        when, data = self.chunks.pop(0)
        self.now = max(self.now, when)
        result, remaining = data[:size], data[size:]
        if remaining:
            self.chunks.insert(0, (when, remaining))
        return result


@pytest.mark.parametrize("channel,subtype", [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)])
def test_itblue_decoder_progress_preserves_each_lens_main_sub_frame(monkeypatch, channel, subtype):
    # Each lens/profile has distinguishable frames. Total assembly takes 20s,
    # but the decoder never stops producing bytes for the 15s inactivity limit.
    first = bytes([channel * 2 + subtype + 1]) * live.FRAME_SIZE
    second = bytes([channel * 2 + subtype + 10]) * live.FRAME_SIZE
    half, quarter = live.FRAME_SIZE // 2, live.FRAME_SIZE // 4
    pipe = ScheduledPipe([(0.0, first[:half]), (10.0, first[half:half + quarter]),
                          (20.0, first[half + quarter:]), (20.1, second)])
    monkeypatch.setattr(live.os, "name", "posix")
    monkeypatch.setattr(live.time, "monotonic", lambda: pipe.now)
    monkeypatch.setattr(live.select, "select", pipe.select)
    stop = threading.Event()
    assert live.LiveStreamSession._read_exact(pipe, live.FRAME_SIZE, stop) == first
    assert live.LiveStreamSession._read_exact(pipe, live.FRAME_SIZE, stop) == second


def test_decoder_progress_does_not_disable_inactivity_watchdog(monkeypatch):
    pipe = ScheduledPipe([(0.0, b"a"), (10.0, b"b"), (40.0, b"c")])
    monkeypatch.setattr(live.os, "name", "posix")
    monkeypatch.setattr(live.time, "monotonic", lambda: pipe.now)
    monkeypatch.setattr(live.select, "select", pipe.select)
    assert live.LiveStreamSession._read_exact(pipe, 3, threading.Event()) == b"ab"
    assert 25.0 <= pipe.now < 25.3

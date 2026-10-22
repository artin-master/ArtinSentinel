"""Lightweight local process metrics for the monitoring status bar."""

import os
import time
from pathlib import Path


def process_sample(pids):
    """Return wall time, CPU seconds and resident MiB for live process IDs."""
    ticks = os.sysconf("SC_CLK_TCK")
    page = os.sysconf("SC_PAGE_SIZE")
    cpu = 0.0
    resident = 0
    for pid in set(pids):
        try:
            stat = Path(f"/proc/{int(pid)}/stat").read_text(encoding="ascii")
            fields = stat.rsplit(") ", 1)[1].split()
            cpu += (int(fields[11]) + int(fields[12])) / ticks
            resident += int(Path(f"/proc/{int(pid)}/statm").read_text(encoding="ascii").split()[1]) * page
        except (OSError, ValueError, IndexError):
            continue
    return time.monotonic(), cpu, resident / (1024 * 1024)


def cpu_percent(previous, current):
    if previous is None:
        return None
    elapsed = current[0] - previous[0]
    return max(0, round(100 * (current[1] - previous[1]) / elapsed)) if elapsed > 0 else None

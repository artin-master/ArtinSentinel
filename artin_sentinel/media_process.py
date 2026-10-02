"""Bounded cleanup of owned media children; no transport or protocol policy."""
from __future__ import annotations


def terminate_media_process(process, grace: float = 0.5) -> None:
    if process is None:
        return
    try:
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=grace)
            except Exception:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=0.5)
                except Exception:
                    pass
        else:
            process.wait(timeout=0.1)
    finally:
        for name in ('stdin', 'stdout', 'stderr'):
            pipe = getattr(process, name, None)
            if pipe is not None:
                try:
                    pipe.close()
                except (OSError, ValueError):
                    pass

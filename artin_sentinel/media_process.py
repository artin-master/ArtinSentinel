"""Bounded cleanup of owned media children; no transport or protocol policy."""
from __future__ import annotations


def terminate_media_process(process, grace: float = 0.5, *, close_pipes: bool = True) -> None:
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
            wait = getattr(process, "wait", None)
            if callable(wait):
                wait(timeout=0.1)
    finally:
        for name in (('stdin', 'stdout', 'stderr') if close_pipes else ()):
            pipe = getattr(process, name, None)
            if pipe is not None and callable(getattr(pipe, "close", None)):
                try:
                    pipe.close()
                except (OSError, ValueError):
                    pass


def media_session_chain(sessions):
    """Snapshot audio predecessors before Stop clears UI/session references."""
    pending = list(sessions)
    result, seen = [], set()
    while pending:
        session = pending.pop(0)
        if session is None or id(session) in seen:
            continue
        seen.add(id(session))
        result.append(session)
        previous = vars(session).get('_previous_session')
        if previous is not None:
            pending.append(previous)
    return result


def wait_media_sessions(sessions, timeout: float = 4.0) -> bool:
    """Wait on one shared shutdown budget after callers requested Stop.

    Native calls remain owned by their worker; Python threads are never killed.
    Any still-owned child is reaped even if a native call exhausted the budget.
    """
    import time
    deadline = time.monotonic() + max(0.0, timeout)
    complete = True
    seen = set()
    for session in media_session_chain(sessions):
        if session is None or id(session) in seen:
            continue
        seen.add(id(session))
        wait = getattr(session, 'wait_closed', None)
        if callable(wait):
            complete = bool(wait(max(0.0, deadline - time.monotonic()))) and complete
        terminate_media_process(getattr(session, '_process', None), grace=0.1)
    return complete

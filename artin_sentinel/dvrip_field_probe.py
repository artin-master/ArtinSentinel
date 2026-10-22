"""One-shot DVRIP field diagnostic, intentionally separate from discovery/UI."""
from __future__ import annotations

from dataclasses import dataclass
import socket
import threading
import time
from typing import Callable

from .xm_dvrip import DvripSession, DvripError, dvrip_error_code, dvrip_video_metadata


_PROBE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class DvripFieldProbeEvent:
    stage: str
    elapsed_ms: int


@dataclass(frozen=True, slots=True)
class DvripFieldProbeResult:
    channel: int
    subtype: int
    login_ret: int | None
    claim_ret: int | None
    start_sent: bool
    packets_received: int
    bytes_received: int
    first_video_packet: bool
    codec: str
    duration_ms: int
    error_code: str
    events: tuple[DvripFieldProbeEvent, ...]
    socket_closed: bool


def probe_dvrip_single_shot(
    host: str,
    username: str,
    password: str,
    *,
    channel: int,
    subtype: int,
    timeout: float = 8.0,
    _session_factory: Callable[..., DvripSession] = DvripSession,
) -> DvripFieldProbeResult:
    """Run one new Login/Claim/Start/media/close sequence, with no retries.

    The returned first-video marker means a DVRIP video keyframe packet was
    received and its codec header parsed. This diagnostic does not start FFmpeg
    or inspect/store video content.
    """
    channel, subtype = int(channel), int(subtype)
    if channel not in (0, 1, 2):
        raise ValueError("Canal DVRIP deve ser 0, 1 ou 2.")
    if subtype not in (0, 1):
        raise ValueError("Subtype DVRIP deve ser 0 (Main) ou 1 (Sub/Extra1).")
    timeout = max(0.1, min(float(timeout), 30.0))
    if not _PROBE_LOCK.acquire(blocking=False):
        raise RuntimeError("Já existe uma sonda DVRIP de campo em execução.")

    started = time.monotonic()
    events: list[DvripFieldProbeEvent] = []
    session = None
    owned_socket = None
    login_ret = claim_ret = None
    start_sent = first_video_packet = False
    packets_received = bytes_received = 0
    codec = error_code = ""
    stage = "session_created"
    media_deadline = 0.0

    def mark(stage: str) -> None:
        events.append(DvripFieldProbeEvent(stage, round((time.monotonic() - started) * 1000)))

    try:
        mark("session_created")
        session = _session_factory(host, username, password, port=34567, timeout=min(3.0, timeout))
        session.connect()
        owned_socket = session.sock
        stage = "connected"
        mark("connected")
        stage = "login"
        session.login()
        login_ret = session.login_reply_code
        mark("login_ok")
        stage = "claim"
        session.monitor_claim(channel, subtype)
        claim_ret = session.monitor_reply_code
        mark("claim_ok")
        stage = "start"
        session.monitor_start(channel, subtype)
        start_sent = True
        stage = "media"
        mark("start_sent")

        media_deadline = time.monotonic() + timeout
        session.media_deadline = media_deadline
        session.media_cancel = threading.Event()
        while time.monotonic() < media_deadline:
            if session.sock is not None:
                session.sock.settimeout(max(0.01, min(session.timeout, media_deadline - time.monotonic())))
            ptype, packet = session.read_media_packet()
            packets_received += 1
            bytes_received += len(packet)
            if ptype in (0xFC, 0xFE):
                codec, _fps, _width, _height = dvrip_video_metadata(packet)
                first_video_packet = True
                mark("first_video_packet")
                break
        if not first_video_packet:
            error_code = "timeout"
    except (DvripError, OSError, TimeoutError, ValueError) as exc:
        if session is not None:
            login_ret = login_ret if login_ret is not None else session.login_reply_code
            claim_ret = claim_ret if claim_ret is not None else session.monitor_reply_code
        error_code = "claim_rejected" if stage == "claim" else dvrip_error_code(exc)
        if error_code == "media_unverified" and media_deadline and time.monotonic() >= media_deadline:
            error_code = "timeout"
        mark("failed_" + error_code)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                error_code = error_code or "close_error"
        socket_closed = session is None or session.sock is None
        if owned_socket is not None:
            socket_closed = socket_closed and bool(getattr(owned_socket, "_closed", False))
        mark("closed" if socket_closed else "close_unconfirmed")
        _PROBE_LOCK.release()

    return DvripFieldProbeResult(
        channel=channel,
        subtype=subtype,
        login_ret=login_ret,
        claim_ret=claim_ret,
        start_sent=start_sent,
        packets_received=packets_received,
        bytes_received=bytes_received,
        first_video_packet=first_video_packet,
        codec=codec,
        duration_ms=round((time.monotonic() - started) * 1000),
        error_code=error_code,
        events=tuple(events),
        socket_closed=socket_closed,
    )

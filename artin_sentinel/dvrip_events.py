"""Opt-in XM/Sofia event subscription; no camera configuration writes.

The OpenIPC/python-dvr dialect uses GUARD_REQ (1500, empty Name) and
AlarmInfo (1504). A successful acknowledgement confirms this dialect only,
not motion/human support on a particular firmware. No alternate IDs are tried.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import socket
import threading
import time
from collections import deque
from queue import Queue, Full

from .xm_dvrip import DvripSession, _HEADER

GUARD_REQ = 1500
ALARM_INFO = 1504
KEEP_ALIVE = 1006
CONFIG_GET = 1042
MAX_PACKET = 64 * 1024
READ_CONFIGS = ("Detect", "Detect.MotionDetect", "Detect.HumanDetection", "Detect.HumanDetect")


class EventProtocolError(RuntimeError):
    """Fixed error codes only; never external exception text."""


class EventSession(DvripSession):
    """A dedicated socket with one reader and bounded, resumable framing."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._buffer = bytearray()
        self.pending = deque(maxlen=64)

    def close(self):
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        super().close()

    def receive(self, deadline=None):
        deadline = deadline or time.monotonic() + self.timeout
        while True:
            if len(self._buffer) >= _HEADER.size:
                magic, version, sid, seq, message, length = _HEADER.unpack(self._buffer[:_HEADER.size])
                if magic != 255 or length > MAX_PACKET:
                    raise EventProtocolError("invalid_packet")
                size = _HEADER.size + length
                if len(self._buffer) >= size:
                    body = bytes(self._buffer[_HEADER.size:size])
                    del self._buffer[:size]
                    try:
                        payload = json.loads(body.rstrip(b"\x00\n"))
                    except (ValueError, UnicodeError):
                        raise EventProtocolError("invalid_json") from None
                    if not isinstance(payload, dict):
                        raise EventProtocolError("invalid_payload")
                    return message, sid, payload
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout()
            sock = self.sock
            if sock is None:
                raise EventProtocolError("closed")
            sock.settimeout(min(remaining, 1.0))
            part = sock.recv(4096)
            if not part:
                raise EventProtocolError("connection_closed")
            self._buffer.extend(part)

    def send_only(self, message, payload):
        if message not in {1000, GUARD_REQ, KEEP_ALIVE, CONFIG_GET}:
            raise EventProtocolError("command_not_allowed")
        if message != 1000:
            names = {GUARD_REQ: ("",), KEEP_ALIVE: ("KeepAlive",), CONFIG_GET: READ_CONFIGS}
            if set(payload) != {"Name", "SessionID"} or payload.get("Name") not in names[message]:
                raise EventProtocolError("command_not_allowed")
        sock = self.sock
        if sock is None:
            raise EventProtocolError("closed")
        raw = json.dumps(payload, separators=(",", ":")).encode() + b"\n\x00"
        sock.sendall(_HEADER.pack(255, 0, self.session, self.sequence, message, len(raw)) + raw)
        self.sequence = (self.sequence + 1) & 0xffffffff

    def _send_json(self, msgid, payload, *, packet_type=0):
        self.send_only(msgid, payload)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                message, sid, reply = self.receive(deadline)
            except socket.timeout:
                continue
            if message == ALARM_INFO and self.session and sid == self.session:
                self.pending.append(reply)
                continue
            if message != msgid + 1 or (self.session and sid != self.session):
                raise EventProtocolError("unexpected_reply")
            self.session = sid or self.session
            if msgid == 1000 and reply.get("Ret") != 100:
                code = "authentication_refused" if reply.get("Ret") in {106, 107, 203} else "login_refused"
                raise EventProtocolError(code)
            return reply
        raise EventProtocolError("response_timeout")

    def subscribe(self):
        reply = self._send_json(GUARD_REQ, {"Name": "", "SessionID": f"0x{self.session:08x}"})
        ret = reply.get("Ret")
        if ret == 100:
            return "yes"
        if ret in {102, 502, 605, 607}:
            return "no"
        raise EventProtocolError("subscription_refused")

    def read_detection_summary(self):
        summaries = []
        for name in READ_CONFIGS:
            reply = self._send_json(CONFIG_GET, {"Name": name, "SessionID": f"0x{self.session:08x}"})
            if reply.get("Ret") == 100:
                summaries.extend(detection_summary(reply.get(name), path=name))
        return tuple(summaries)


def detection_summary(value, path="", depth=0):
    """Allowlist typed configuration evidence, never raw strings/payloads.

    Settings describe configured linkage, not physical light/siren state.
    """
    containers = {"MotionDetect", "HumanDetection", "HumanDetect", "EventHandler", "value"}
    booleans = {"Enable", "BeepEnable", "FlashEnable", "AlarmOutEnable", "RecordEnable", "MsgtoNetEnable"}
    result = []
    if depth > 5:
        return result
    if isinstance(value, list):
        for index, item in enumerate(value[:64]):
            result.extend(detection_summary(item, f"{path}[{index}]", depth + 1))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in containers:
                result.extend(detection_summary(item, f"{path}.{key}", depth + 1))
            elif key in booleans and type(item) is bool:
                result.append((f"{path}.{key}", item))
            elif key == "Level" and type(item) is int and 0 <= item <= 100:
                result.append((f"{path}.Level", item))
    return result


@dataclass(frozen=True)
class EventDiagnostics:
    support: str = "unknown"
    active: bool = False
    state: str = "stopped"
    last_reconnect: float | None = None
    error_code: str = ""
    config: tuple = ()
    dropped: int = 0


class EventWorker:
    """One opt-in session, bounded queue/backoff; consumer runs on the Qt thread."""
    def __init__(self, host, username, password, *, session_factory=EventSession):
        self._args = (host, username, password)
        self._factory = session_factory
        self.events = Queue(maxsize=128)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._session = None
        self._thread = None
        self._diagnostics = EventDiagnostics()

    def snapshot(self):
        with self._lock:
            return self._diagnostics

    def _update(self, **values):
        with self._lock:
            self._diagnostics = replace(self._diagnostics, **values)

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="DvripEvents", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            session = self._session
        if session:
            session.close()

    def wait(self, timeout=4):
        if self._thread:
            self._thread.join(timeout)
        return not self._thread or not self._thread.is_alive()

    def _emit(self, payload):
        # Normalize here: raw packets never cross to the GUI or local history.
        from .camera_events import normalize_event
        event = normalize_event(payload)
        if event and not self._stop.is_set():
            try:
                self.events.put_nowait(event)
            except Full:
                self._update(dropped=self.snapshot().dropped + 1)

    def _run(self):
        delay = 1.0
        while not self._stop.is_set():
            session = self._factory(*self._args, timeout=3)
            with self._lock:
                self._session = session
            started = time.monotonic()
            try:
                if self._stop.is_set():
                    break
                self._update(state="connecting", error_code="")
                reply = session.login()
                if self._stop.is_set():
                    break
                support = session.subscribe()
                self._update(support=support, active=support == "yes", state="active" if support == "yes" else "unsupported")
                if support == "no":
                    break
                self._update(config=session.read_detection_summary())
                interval = reply.get("AliveInterval", 20)
                interval = max(5, min(interval if type(interval) in (int, float) else 20, 30))
                next_keepalive = time.monotonic() + interval
                ack_deadline = None
                while not self._stop.is_set():
                    while session.pending:
                        self._emit(session.pending.popleft())
                    now = time.monotonic()
                    if ack_deadline and now > ack_deadline:
                        raise EventProtocolError("keepalive_timeout")
                    if now >= next_keepalive and ack_deadline is None:
                        session.send_only(KEEP_ALIVE, {"Name": "KeepAlive", "SessionID": f"0x{session.session:08x}"})
                        ack_deadline = now + 5
                        next_keepalive = now + interval
                    try:
                        message, sid, payload = session.receive(time.monotonic() + 1)
                    except socket.timeout:
                        continue
                    if sid != session.session:
                        raise EventProtocolError("session_mismatch")
                    if message == ALARM_INFO:
                        self._emit(payload)
                    elif message == KEEP_ALIVE + 1 and payload.get("Ret") == 100:
                        ack_deadline = None
                    else:
                        raise EventProtocolError("unexpected_event_packet")
            except Exception as exc:
                # No arbitrary exception messages, credentials or remote payloads.
                allowed = {"invalid_packet", "invalid_json", "invalid_payload", "unexpected_reply", "subscription_refused", "session_mismatch", "keepalive_timeout", "unexpected_event_packet", "connection_closed", "response_timeout", "authentication_refused", "login_refused"}
                code = str(exc) if isinstance(exc, EventProtocolError) and str(exc) in allowed else "communication_error"
                self._update(active=False, state="reconnecting", error_code=code)
                if code in {"subscription_refused", "authentication_refused", "login_refused"}:
                    break
            finally:
                session.close()
                with self._lock:
                    self._session = None
            if self._stop.is_set() or self.snapshot().support == "no":
                break
            if time.monotonic() - started >= 60:
                delay = 1
            self._update(active=False, last_reconnect=time.time())
            if self._stop.wait(delay):
                break
            delay = min(delay * 2, 60)
        self._update(active=False, state="stopped" if self._stop.is_set() else ("unsupported" if self.snapshot().support == "no" else "refused"))

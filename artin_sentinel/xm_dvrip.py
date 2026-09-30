from __future__ import annotations

"""Minimal Xiongmai/Sofia DVRIP client used for explicit local PTZ control.

This module intentionally implements only login and operator-requested PTZ on
TCP/34567. It does not change device configuration and it never logs
credentials or the Sofia password hash.
"""

from dataclasses import dataclass
import hashlib
import json
import socket
import struct
import shutil
import subprocess
import time


_HEADER = struct.Struct("<BB2xII2xHI")
_OK = {100, 515}


class DvripError(RuntimeError):
    pass


def sofia_hash(password: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    digest = hashlib.md5((password or "").encode("utf-8")).digest()
    return "".join(chars[(digest[i] + digest[i + 1]) % 62] for i in range(0, 16, 2))


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise DvripError("conexão DVRIP encerrada pelo equipamento")
        data.extend(part)
    return bytes(data)


@dataclass(slots=True)
class DvripSession:
    host: str
    username: str
    password: str
    port: int = 34567
    timeout: float = 3.0
    sock: socket.socket | None = None
    session: int = 0
    sequence: int = 0
    media_buffer: bytes = b""

    def connect(self) -> None:
        if self.sock is not None:
            return
        try:
            self.sock = socket.create_connection((self.host, int(self.port)), timeout=self.timeout)
            self.sock.settimeout(self.timeout)
        except OSError as exc:
            raise DvripError(f"DVRIP TCP/{self.port} indisponível: {exc}") from exc

    def attach_authenticated_session(self, session: int, sequence: int) -> None:
        """Attach a secondary DVRIP TCP connection to an existing login session.

        XM/Sofia uses one logical authenticated session across control, media and
        talk sockets. Secondary sockets must reuse both the SessionID and the
        session-wide monotonic command sequence; they must *not* authenticate a
        second independent session. This method only adopts already-authenticated
        state after ``connect()`` and never sends a command by itself.
        """
        self.connect()
        self.session = int(session) & 0xFFFFFFFF
        self.sequence = int(sequence) & 0xFFFFFFFF

    def sync_sequence_from(self, other: "DvripSession") -> None:
        """Continue the shared session command sequence after another socket."""
        self.sequence = int(other.sequence) & 0xFFFFFFFF

    def close(self) -> None:
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def __enter__(self) -> "DvripSession":
        self.connect()
        self.login()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _send_json(self, msgid: int, payload: dict, *, packet_type: int = 0) -> dict:
        if self.sock is None:
            raise DvripError("sessão DVRIP não conectada")
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        packet = _HEADER.pack(0xFF, int(packet_type) & 0xFF, int(self.session), int(self.sequence), int(msgid), len(raw) + 2) + raw + b"\n\x00"
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        try:
            self.sock.sendall(packet)
            header = _recv_exact(self.sock, _HEADER.size)
            magic, _version, session, _seq, _response_id, length = _HEADER.unpack(header)
            if magic != 0xFF:
                raise DvripError("resposta DVRIP inválida")
            body = _recv_exact(self.sock, int(length)) if length else b""
        except (OSError, socket.timeout) as exc:
            raise DvripError(f"falha de comunicação DVRIP: {exc}") from exc
        self.session = int(session or self.session)
        body = body.rstrip(b"\x00\n")
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            raise DvripError("resposta DVRIP não contém JSON válido") from exc

    def login(self) -> dict:
        self.connect()
        reply = self._send_json(
            1000,
            {
                "EncryptType": "MD5",
                "LoginType": "DVRIP-Web",
                "PassWord": sofia_hash(self.password),
                "UserName": self.username,
            },
        )
        ret = int(reply.get("Ret", -1))
        if ret not in _OK:
            messages = {
                203: "credencial DVRIP recusada",
                107: "acesso DVRIP negado",
                102: "DVRIP não suportado",
            }
            raise DvripError(messages.get(ret, f"login DVRIP recusado (Ret={ret})"))
        sid = reply.get("SessionID")
        if isinstance(sid, str):
            try:
                self.session = int(sid, 16)
            except ValueError:
                pass
        return reply

    def _json_payload_bytes(self, payload: dict) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n\x00"

    def monitor_parameter(self, channel: int = 0, subtype: int = 0) -> dict:
        return {
            "Channel": max(0, int(channel)),
            "CombinMode": "NONE",
            "StreamType": "Extra1" if int(subtype) == 1 else "Main",
            "TransMode": "TCP",
        }

    def monitor_claim(self, channel: int = 0, subtype: int = 0) -> dict:
        payload = {
            "Name": "OPMonitor",
            "SessionID": f"0x{self.session:08x}",
            "OPMonitor": {"Action": "Claim", "Parameter": self.monitor_parameter(channel, subtype)},
        }
        reply = self._send_json(1413, payload)
        ret = int(reply.get("Ret", 100 if not reply else -1))
        if ret not in _OK:
            raise DvripError(f"claim de monitor DVRIP recusado (Ret={ret})")
        return reply

    def monitor_start(self, channel: int = 0, subtype: int = 0) -> None:
        payload = {
            "Name": "OPMonitor",
            "SessionID": f"0x{self.session:08x}",
            "OPMonitor": {"Action": "Start", "Parameter": self.monitor_parameter(channel, subtype)},
        }
        # Xiongmai/Sofia starts media immediately after this command; waiting for
        # a JSON response here can consume the first media chunk on some firmware.
        self._send_binary_no_reply(1410, self._json_payload_bytes(payload))

    def read_stream_chunk(self) -> tuple[int, bytes]:
        if self.sock is None:
            raise DvripError("sessão DVRIP não conectada")
        try:
            header = _recv_exact(self.sock, _HEADER.size)
            magic, _version, session, _seq, response_id, length = _HEADER.unpack(header)
            if magic != 0xFF:
                raise DvripError("chunk DVRIP inválido")
            body = _recv_exact(self.sock, int(length)) if length else b""
        except (OSError, socket.timeout) as exc:
            raise DvripError(f"falha ao receber mídia DVRIP: {exc}") from exc
        self.session = int(session or self.session)
        return int(response_id), body

    def read_media_packet(self) -> tuple[int, bytes]:
        """Read one proprietary XM media packet from OPMonitor chunks."""
        buf = bytearray(self.media_buffer)
        while True:
            # Need at least a complete proprietary media header.
            while len(buf) < 16:
                _msgid, body = self.read_stream_chunk()
                stripped = body.lstrip()
                if stripped.startswith(b"{"):
                    # Ignore optional control acknowledgement interleaved before media.
                    continue
                buf.extend(body)
            prefix = bytes(buf[:3])
            if prefix != b"\x00\x00\x01":
                pos = bytes(buf).find(b"\x00\x00\x01")
                if pos < 0:
                    if len(buf) > 1024 * 1024:
                        buf.clear()
                    _msgid, body = self.read_stream_chunk()
                    buf.extend(body)
                    continue
                del buf[:pos]
                if len(buf) < 16:
                    continue
            ptype = int(buf[3])
            if ptype in (0xFC, 0xFE):
                size = int.from_bytes(buf[12:16], "little") + 16
            elif ptype == 0xFD:
                size = int.from_bytes(buf[4:8], "little") + 8
            elif ptype in (0xFA, 0xF9):
                size = int.from_bytes(buf[6:8], "little") + 8
            else:
                # Unknown packet marker: resync at the next Annex-like prefix.
                del buf[:3]
                continue
            while len(buf) < size:
                _msgid, body = self.read_stream_chunk()
                buf.extend(body)
            packet = bytes(buf[:size])
            del buf[:size]
            self.media_buffer = bytes(buf)
            return ptype, packet

    def get_config(self, name: str) -> dict:
        """Read one DVRIP/Sofia configuration object (message 1042).

        This is a GET-only operation.  The caller is responsible for exposing
        only sanitized, non-secret fields to logs/reports.
        """
        payload = {
            "Name": str(name),
            "SessionID": f"0x{self.session:08x}",
        }
        reply = self._send_json(1042, payload)
        ret = int(reply.get("Ret", -1))
        if ret not in _OK:
            raise DvripError(f"consulta DVRIP {name} recusada (Ret={ret})")
        value = reply.get(str(name), {})
        return value if isinstance(value, dict) else {"value": value}

    def ptz(self, command: str, *, channel: int = 0, step: int = 5, start: bool = True) -> dict:
        step = max(1, min(int(step), 8))
        payload = {
            "Name": "OPPTZControl",
            "SessionID": f"0x{self.session:08x}",
            "OPPTZControl": {
                "Command": str(command),
                "Parameter": {
                    "AUX": {"Number": 0, "Status": "On"},
                    "Channel": max(0, int(channel)),
                    "MenuOpts": "Enter",
                    "POINT": {"bottom": 0, "left": 0, "right": 0, "top": 0},
                    "Pattern": "SetBegin",
                    "Preset": 65535 if start else -1,
                    "Step": step,
                    "Tour": 0,
                },
            },
        }
        reply = self._send_json(1400, payload)
        ret = int(reply.get("Ret", 100 if not reply else -1))
        if ret not in _OK:
            raise DvripError(f"comando PTZ DVRIP recusado (Ret={ret})")
        return reply

    def _send_binary_no_reply(
        self, msgid: int, payload: bytes, *, sequence_override: int | None = None, packet_type: int = 0
    ) -> None:
        """Send one DVRIP binary data packet without waiting for JSON reply.

        XM/Sofia talk-audio captures use sequence zero for every 1432 data
        frame. Control/JSON packets keep the normal monotonic sequence.
        """
        if self.sock is None:
            raise DvripError("sessão DVRIP não conectada")
        raw = bytes(payload or b"")
        seq = int(self.sequence if sequence_override is None else sequence_override)
        packet = _HEADER.pack(0xFF, int(packet_type) & 0xFF, int(self.session), seq, int(msgid), len(raw)) + raw
        if sequence_override is None:
            self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        try:
            self.sock.sendall(packet)
        except (OSError, socket.timeout) as exc:
            raise DvripError(f"falha ao transmitir áudio DVRIP: {exc}") from exc

    @staticmethod
    def _talk_payload(session: int, action: str, *, include_format: bool = False) -> dict:
        optalk = {"Action": str(action)}
        if include_format:
            # Sofia's control JSON uses SampleRate=8 to mean 8 kHz. The raw
            # media stream itself remains 8000 Hz G.711 A-law.
            optalk["AudioFormat"] = {
                "BitRate": 0,
                "EncodeType": "G711_ALAW",
                "SampleBit": 8,
                "SampleRate": 8,
            }
        return {
            "Name": "OPTalk",
            "SessionID": f"0x{int(session):010x}",
            "OPTalk": optalk,
        }

    def talk_claim(self) -> dict:
        # Captured XM/iCSee talk frames use DVRIP type byte 0x01. Keep generic
        # login/PTZ compatibility unchanged while matching the talk channel.
        reply = self._send_json(1434, self._talk_payload(self.session, "Claim", include_format=True), packet_type=1)
        ret = int(reply.get("Ret", 100 if not reply else -1))
        if ret not in _OK:
            raise DvripError(f"claim de áudio DVRIP recusado (Ret={ret})")
        return reply

    def talk_start(self) -> dict:
        reply = self._send_json(1430, self._talk_payload(self.session, "Start"), packet_type=1)
        ret = int(reply.get("Ret", 100 if not reply else -1))
        if ret not in _OK:
            raise DvripError(f"início de áudio DVRIP recusado (Ret={ret})")
        return reply

    def talk_start_no_reply(self) -> None:
        """Send OPTalk Start exactly as field-working XM clients do.

        Some firmware interleaves talk audio/control data immediately after
        Start, so waiting synchronously for JSON can consume unrelated frames.
        """
        self._send_binary_no_reply(
            1430, self._json_payload_bytes(self._talk_payload(self.session, "Start")), packet_type=1
        )

    def talk_stop(self) -> dict:
        reply = self._send_json(1430, self._talk_payload(self.session, "Stop"), packet_type=1)
        ret = int(reply.get("Ret", 100 if not reply else -1))
        if ret not in _OK:
            raise DvripError(f"fim de áudio DVRIP recusado (Ret={ret})")
        return reply

    def talk_stop_no_reply(self) -> None:
        self._send_binary_no_reply(
            1430, self._json_payload_bytes(self._talk_payload(self.session, "Stop")), packet_type=1
        )

    def drain_pending(self, limit: int = 65536) -> int:
        """Best-effort discard of pending talk/control bytes without blocking.

        The vendor protocol can send downstream talk audio while upstream audio
        is active. Draining prevents the receive buffer from filling during a
        short PTT session; no configuration data is written or interpreted.
        """
        sock = self.sock
        if sock is None:
            return 0
        total = 0
        old_timeout = sock.gettimeout()
        try:
            sock.setblocking(False)
            while total < max(1, int(limit)):
                try:
                    data = sock.recv(min(16384, int(limit) - total))
                except (BlockingIOError, InterruptedError):
                    break
                if not data:
                    break
                total += len(data)
        finally:
            sock.settimeout(old_timeout)
        return total

    def send_talk_audio(self, alaw_payload: bytes) -> None:
        """Send one G.711 A-law talkback chunk (OPTalk data / msg 1432)."""
        if not alaw_payload:
            return
        # Sofia audio frame header observed by open implementations: signature
        # 000001fa, codec 0x0e=G711A, sample-rate index 0x02=8kHz.
        audio_header = b"\x00\x00\x01\xfa\x0e\x02\x40\x01"
        self._send_binary_no_reply(
            1432, audio_header + bytes(alaw_payload), sequence_override=0, packet_type=1
        )


@dataclass(slots=True)
class DvripMediaProbe:
    ok: bool
    codec: str = ""
    fps: int = 0
    detail: str = ""


def probe_dvrip_media(
    host: str, username: str, password: str, *, channel: int = 0, subtype: int = 0, timeout: float = 4.0
) -> DvripMediaProbe:
    """Bounded read-only OPMonitor probe used for native multi-lens discovery."""
    deadline = __import__("time").monotonic() + max(1.0, float(timeout))
    try:
        with DvripSession(host, username, password, timeout=min(2.5, float(timeout))) as session:
            session.monitor_claim(channel, subtype)
            session.monitor_start(channel, subtype)
            while __import__("time").monotonic() < deadline:
                ptype, packet = session.read_media_packet()
                if ptype not in (0xFC, 0xFE, 0xFD):
                    continue
                if ptype == 0xFD:
                    # Wait for a keyframe so codec/fps metadata is available.
                    continue
                media_code = int(packet[4]) if len(packet) > 5 else 0
                fps = int(packet[5]) if len(packet) > 5 else 0
                if media_code in (0x02, 0x12):
                    codec = "h264"
                elif media_code in (0x03, 0x13, 0x43, 0x53):
                    codec = "hevc"
                else:
                    return DvripMediaProbe(False, detail=f"codec DVRIP não suportado: 0x{media_code:02x}")
                return DvripMediaProbe(True, codec=codec, fps=fps, detail=f"DVRIP canal {channel} {codec.upper()} {fps or '?'} fps")
    except DvripError as exc:
        return DvripMediaProbe(False, detail=str(exc))
    return DvripMediaProbe(False, detail=f"DVRIP canal {channel} sem vídeo no limite de tempo")


def dvrip_frame_signature(host: str, username: str, password: str, *, channel: int = 0,
                          subtype: int = 0, timeout: float = 4.0) -> int | None:
    """Decode a bounded native frame for comparison with RTSP and other lenses.

    A successful OPMonitor response alone does not identify a physical lens:
    some XM firmware returns the PTZ picture for several channel numbers.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    deadline = time.monotonic() + max(1.0, timeout)
    data = bytearray()
    codec = ""
    try:
        with DvripSession(host, username, password, timeout=min(1.5, timeout)) as session:
            session.monitor_claim(channel, subtype)
            session.monitor_start(channel, subtype)
            while time.monotonic() < deadline and len(data) < 4 * 1024 * 1024:
                ptype, packet = session.read_media_packet()
                if ptype in (0xFC, 0xFE):
                    media_code = packet[4] if len(packet) > 5 else 0
                    codec = ("h264" if media_code in (0x02, 0x12) else
                             "hevc" if media_code in (0x03, 0x13, 0x43, 0x53) else "")
                    if not codec:
                        return None
                    data.extend(packet[16:])
                elif ptype == 0xFD and codec:
                    data.extend(packet[8:])
                if codec and len(data) >= 128 * 1024:
                    break
    except (DvripError, OSError):
        return None
    if not data or not codec:
        return None
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
           "-f", codec, "-i", "pipe:0", "-frames:v", "1",
           "-vf", "crop=trunc(iw*0.72):trunc(ih*0.62):trunc(iw*0.14):trunc(ih*0.19),scale=16:9,format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    try:
        cp = subprocess.run(cmd, input=bytes(data), capture_output=True, timeout=2.0, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if cp.returncode != 0 or len(cp.stdout) < 144:
        return None
    pixels = cp.stdout[:144]
    avg = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | int(value >= avg)
    return bits


# Field validation on IT-Blue X3-WE2Q/XM535D1 showed that this OEM
# firmware exposes the horizontal DVRIP direction names mirrored relative to
# the physical camera. Keep the correction isolated to the XM backend so ONVIF
# and other manufacturers retain their normal coordinate system.
_DIRECTION_COMMANDS = {
    "up": "DirectionUp",
    "down": "DirectionDown",
    "left": "DirectionRight",
    "right": "DirectionLeft",
    "up-left": "DirectionRightUp",
    "down-left": "DirectionRightDown",
    "up-right": "DirectionLeftUp",
    "down-right": "DirectionLeftDown",
    "zoom-in": "ZoomTile",
    "zoom-out": "ZoomWide",
}


def dvrip_ptz_command(direction: str) -> str:
    try:
        return _DIRECTION_COMMANDS[str(direction or "").lower()]
    except KeyError as exc:
        raise ValueError(f"Direção PTZ DVRIP inválida: {direction}") from exc


def dvrip_ptz_start(host: str, username: str, password: str, direction: str, speed: float = 0.45, *, channel: int = 0) -> str:
    step = max(1, min(8, round(float(speed) * 8)))
    command = dvrip_ptz_command(direction)
    with DvripSession(host, username, password) as session:
        session.ptz(command, channel=channel, step=step, start=True)
    return f"PTZ DVRIP/XM: {direction}"


def dvrip_ptz_stop(host: str, username: str, password: str, direction: str, speed: float = 0.45, *, channel: int = 0) -> str:
    # Sofia stops the active operation by repeating the same command with
    # Preset=-1. The last active direction is therefore kept by the UI.
    step = max(1, min(8, round(float(speed) * 8)))
    command = dvrip_ptz_command(direction or "right")
    with DvripSession(host, username, password) as session:
        session.ptz(command, channel=channel, step=step, start=False)
    return "PTZ DVRIP/XM: stop"


def dvrip_probe(host: str, username: str, password: str, *, timeout: float = 3.0) -> dict:
    """Authenticate only and return non-secret capability hints from LoginReply."""
    with DvripSession(host, username, password, timeout=timeout) as session:
        # login() already ran in __enter__; no configuration changes are made.
        return {"connected": True, "port": session.port}


def _count_sequence(value) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        best = 0
        for item in value.values():
            best = max(best, _count_sequence(item))
        return best
    return 0


def dvrip_multilens_hints(host: str, username: str, password: str, *, timeout: float = 3.0) -> dict:
    """Read safe XM/Sofia configuration hints for multi-lens mapping.

    The probe never changes configuration.  It intentionally returns only
    counts/booleans and the names of successful config objects; raw payloads
    may contain installation-specific data and are not exposed.
    """
    names = ("Camera", "Simplify.Encode", "EncodeCapability", "SystemFunction", "General")
    successful = []
    channel_count = 0
    with DvripSession(host, username, password, timeout=timeout) as session:
        for name in names:
            try:
                data = session.get_config(name)
            except DvripError:
                continue
            successful.append(name)
            # Known SDK payloads commonly expose ChannelNum directly or arrays
            # of per-channel encode/camera objects.  Use both, conservatively.
            stack = [data]
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    for key, value in item.items():
                        lower = str(key).lower()
                        if lower in {"channelnum", "channelcount", "chnnum"}:
                            try:
                                channel_count = max(channel_count, int(value))
                            except (TypeError, ValueError):
                                pass
                        if isinstance(value, (dict, list)):
                            stack.append(value)
                elif isinstance(item, list):
                    channel_count = max(channel_count, len(item))
                    stack.extend(item)
            channel_count = max(channel_count, _count_sequence(data))
    return {
        "connected": True,
        "config_objects": tuple(successful),
        "channel_count_hint": min(max(channel_count, 0), 16),
    }

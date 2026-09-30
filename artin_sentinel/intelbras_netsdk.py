from __future__ import annotations

"""Minimal ctypes bridge for the official Intelbras/Dahua NetSDK talkback APIs.

0.2.42 exposes the narrow subset needed for direct, local
voice talk testing against known Intelbras cameras.  It does not implement
cloud/P2P discovery and it does not persist credentials or SDK session data.
"""

from dataclasses import dataclass, field
import ctypes
from ctypes import (
    c_bool, c_byte, c_char, c_char_p, c_int, c_long, c_ubyte, c_uint, c_ushort,
    c_void_p, POINTER, Structure, byref, sizeof,
)
from pathlib import Path
import io
import os
import platform
import shutil
import tarfile
import threading
import zipfile


DH_SERIALNO_LEN = 48
DH_DEVSTATE_TALK_ECTYPE = 0x0009

# EM_LOGIN_SPAC_CAP_TYPE
EM_LOGIN_SPEC_CAP_TCP = 0

# EM_USEDEV_MODE
DH_TALK_CLIENT_MODE = 0
DH_TALK_SERVER_MODE = 1
DH_TALK_ENCODE_TYPE = 2
DH_TALK_TALK_CHANNEL = 5
DH_TALK_SPEAK_PARAM = 8
DH_TALK_MODE3 = 9
DH_TALK_TRANSFER_MODE = 11

EM_DEV_PROTOCOL_UNKNOWN = 0
EM_DEV_PROTOCOL_V2 = 1
EM_DEV_PROTOCOL_V3 = 2

# __TALK_CODING_TYPE
DH_TALK_DEFAULT = 0
DH_TALK_PCM = 1
DH_TALK_G711A = 2
DH_TALK_AMR = 3
DH_TALK_G711U = 4
DH_TALK_G726 = 5
DH_TALK_AAC = 8

_TALK_NAMES = {
    DH_TALK_DEFAULT: "PCM sem cabeçalho",
    DH_TALK_PCM: "PCM",
    DH_TALK_G711A: "G.711A",
    DH_TALK_AMR: "AMR",
    DH_TALK_G711U: "G.711u",
    DH_TALK_G726: "G.726",
    DH_TALK_AAC: "AAC",
}


class NetSDKUnavailable(RuntimeError):
    pass


class NetSDKError(RuntimeError):
    pass


class NET_DEVICEINFO_Ex(Structure):
    _fields_ = [
        ("sSerialNumber", c_ubyte * DH_SERIALNO_LEN),
        ("nAlarmInPortNum", c_int),
        ("nAlarmOutPortNum", c_int),
        ("nDiskNum", c_int),
        ("nDVRType", c_int),
        ("nChanNum", c_int),
        ("byLimitLoginTime", c_ubyte),
        ("byLeftLogTimes", c_ubyte),
        ("bReserved", c_ubyte * 2),
        ("nLockLeftTime", c_int),
        ("Reserved", c_char * 24),
    ]


class DHDEV_TALKDECODE_INFO(Structure):
    _fields_ = [
        ("encodeType", c_int),
        ("nAudioBit", c_int),
        ("dwSampleRate", c_uint),
        ("nPacketPeriod", c_int),
        ("reserved", c_char * 60),
    ]


class DHDEV_TALKFORMAT_LIST(Structure):
    _fields_ = [
        ("nSupportNum", c_int),
        ("type", DHDEV_TALKDECODE_INFO * 64),
        ("reserved", c_char * 64),
    ]


class NET_SPEAK_PARAM(Structure):
    _fields_ = [
        ("dwSize", c_uint),
        ("nMode", c_int),
        ("nSpeakerChannel", c_int),
        ("bEnableWait", c_int),
    ]


class NET_TALK_TRANSFER_PARAM(Structure):
    _fields_ = [
        ("dwSize", c_uint),
        ("bTransfer", c_int),
    ]


class NET_TALK_VIDEO_FORMAT(Structure):
    _fields_ = [
        ("dwSize", c_uint),
        ("dwCompression", c_uint),
        ("nFrequency", c_int),
    ]


class NET_TALK_EX(Structure):
    _fields_ = [
        ("dwSize", c_uint),
        ("nChannel", c_int),
        ("nAudioPort", c_int),
        ("nWaitTime", c_int),
        ("hVideoWnd", c_void_p),
        ("stuVideoFmt", NET_TALK_VIDEO_FORMAT),
        ("szMulticastAddr", c_char * 40),
        ("wMulticastLocalPort", c_ushort),
        ("wMulticastRemotePort", c_ushort),
    ]


@dataclass(frozen=True, slots=True)
class TalkFormat:
    encode_type: int
    sample_rate: int
    audio_bits: int
    packet_period_ms: int

    @property
    def name(self) -> str:
        return _TALK_NAMES.get(self.encode_type, f"codec {self.encode_type}")


@dataclass(slots=True)
class LoginResult:
    handle: int
    port: int
    channels: int = 0
    serial: str = ""
    error_code: int = 0


@dataclass(slots=True)
class NetSDKRuntimeInfo:
    available: bool
    detail: str
    library_path: str = ""
    architecture: str = ""
    bundled_libraries: list[str] = field(default_factory=list)


OFFICIAL_SDK_TAR_BASENAME = "General_NetSDK_Eng_Linux64_IS_V3.050.0000005.4.R.190306.tar.gz"
REQUIRED_RUNTIME_LIBS = {"libdhnetsdk.so"}
OPTIONAL_RUNTIME_LIBS = {
    "libInfra.so", "libNetFramework.so", "libStream.so", "libStreamSvr.so",
    "libavnetsdk.so", "libdhconfigsdk.so",
}
REFERENCE_AUDIO_NAME = "localRecordAudio.dav"


def vendor_install_directory() -> Path:
    override = os.environ.get("ARTIN_SENTINEL_NETSDK_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "artin-sentinel" / "vendor" / "intelbras-netsdk"


def reference_audio_path() -> Path:
    return vendor_install_directory() / REFERENCE_AUDIO_NAME


def _safe_archive_name(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def install_from_official_archive(archive: str | Path, target: str | Path | None = None) -> list[str]:
    """Import only the Linux runtime and 05.Talk reference audio from Intelbras' official ZIP.

    The vendor archive is supplied by the operator; Sentinel does not redistribute it.
    Files are copied into the persistent per-user vendor directory so future application
    updates can reuse the same runtime.
    """
    archive_path = Path(archive).expanduser().resolve()
    target_path = Path(target).expanduser().resolve() if target is not None else vendor_install_directory().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    target_path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path) as zf:
        candidates = [
            name for name in zf.namelist()
            if name.endswith(".tar.gz") and "NetSDK 3.050/Linux/" in name
        ]
        if not candidates:
            raise RuntimeError("arquivo Linux64 NetSDK 3.050 não encontrado dentro do ZIP oficial")
        member = next((name for name in candidates if name.endswith(OFFICIAL_SDK_TAR_BASENAME)), candidates[0])
        if not _safe_archive_name(member):
            raise RuntimeError("caminho inseguro no ZIP do NetSDK")
        tar_bytes = zf.read(member)

    imported: list[str] = []
    wanted = REQUIRED_RUNTIME_LIBS | OPTIONAL_RUNTIME_LIBS
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tf:
        files = [m for m in tf.getmembers() if m.isfile()]
        by_basename = {Path(m.name).name: m for m in files if m.name.startswith("bin/")}
        missing = REQUIRED_RUNTIME_LIBS - set(by_basename)
        if missing:
            raise RuntimeError("SDK não contém biblioteca obrigatória: " + ", ".join(sorted(missing)))
        for name in sorted(wanted & set(by_basename)):
            member = by_basename[name]
            if not _safe_archive_name(member.name):
                raise RuntimeError(f"caminho inseguro no TAR: {member.name}")
            src = tf.extractfile(member)
            if src is None:
                continue
            dst = target_path / name
            tmp = dst.with_suffix(dst.suffix + ".tmp")
            with tmp.open("wb") as out:
                shutil.copyfileobj(src, out)
            tmp.chmod(0o755)
            tmp.replace(dst)
            imported.append(name)

        reference = next((m for m in files if m.name.endswith("demo/05.Talk/localRecordAudio.dav")), None)
        if reference is not None:
            if not _safe_archive_name(reference.name):
                raise RuntimeError("caminho inseguro no áudio de referência")
            src = tf.extractfile(reference)
            if src is not None:
                dst = target_path / REFERENCE_AUDIO_NAME
                tmp = dst.with_suffix(dst.suffix + ".tmp")
                with tmp.open("wb") as out:
                    shutil.copyfileobj(src, out)
                tmp.chmod(0o644)
                tmp.replace(dst)
                imported.append(REFERENCE_AUDIO_NAME)
    return imported


def vendor_directory() -> Path:
    """Resolve the local Intelbras NetSDK runtime directory.

    Vendor binaries are intentionally not redistributed in the Sentinel ZIP.
    The installer/helper imports the official SDK supplied by Intelbras into the
    per-user data directory. An environment override is kept for developers.
    """
    candidates: list[Path] = []
    override = os.environ.get("ARTIN_SENTINEL_NETSDK_DIR", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(vendor_install_directory())
    # Development-only fallback: never required by the installed wheel.
    candidates.append(Path(__file__).resolve().parent / "vendor" / "intelbras" / "linux-x86_64")
    for root in candidates:
        if (root / "libdhnetsdk.so").exists():
            return root
    return candidates[0] if candidates else Path()


def runtime_info() -> NetSDKRuntimeInfo:
    arch = platform.machine().lower()
    root = vendor_directory()
    lib = root / "libdhnetsdk.so"
    if platform.system().lower() != "linux":
        return NetSDKRuntimeInfo(False, "NetSDK suportado nesta versão apenas no Linux", architecture=arch)
    if arch not in {"x86_64", "amd64"}:
        return NetSDKRuntimeInfo(False, f"arquitetura {arch} ainda não empacotada", architecture=arch)
    if not lib.exists():
        return NetSDKRuntimeInfo(False, "libdhnetsdk.so não encontrada", architecture=arch)
    libs = sorted(p.name for p in root.glob("*.so"))
    return NetSDKRuntimeInfo(True, "NetSDK Intelbras disponível", str(lib), arch, libs)


class IntelbrasNetSDK:
    """Process-wide loader and narrow wrapper around the official NetSDK."""

    _instance: "IntelbrasNetSDK | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "IntelbrasNetSDK":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        info = runtime_info()
        if not info.available:
            raise NetSDKUnavailable(info.detail)
        self.info = info
        self._vendor_libs: list[ctypes.CDLL] = []
        root = vendor_directory()
        # Preload companion libraries globally because this 2019 NetSDK build
        # loads some components dynamically by soname at runtime.
        preload_order = [
            "libInfra.so", "libStream.so", "libNetFramework.so",
            "libdhconfigsdk.so", "libavnetsdk.so", "libStreamSvr.so",
        ]
        mode = getattr(ctypes, "RTLD_GLOBAL", 0)
        for name in preload_order:
            path = root / name
            if path.exists():
                try:
                    self._vendor_libs.append(ctypes.CDLL(str(path), mode=mode))
                except OSError:
                    # libdhnetsdk may not need every optional peer for talkback.
                    pass
        try:
            self.lib = ctypes.CDLL(str(root / "libdhnetsdk.so"), mode=mode)
        except OSError as exc:
            raise NetSDKUnavailable(f"falha ao carregar libdhnetsdk.so: {exc}") from exc
        self._bind()
        # CLIENT_Init accepts a NULL disconnect callback.
        if not bool(self.lib.CLIENT_Init(None, 0)):
            raise NetSDKUnavailable(f"CLIENT_Init falhou (0x{self.last_error():08x})")
        # Keep field tests bounded. The SDK's default connection timeout is long.
        self.lib.CLIENT_SetConnectTime(1800, 1)

    def _bind(self) -> None:
        lib = self.lib
        lib.CLIENT_Init.argtypes = [c_void_p, c_long]
        lib.CLIENT_Init.restype = c_int
        lib.CLIENT_SetConnectTime.argtypes = [c_int, c_int]
        lib.CLIENT_SetConnectTime.restype = None
        lib.CLIENT_GetLastError.argtypes = []
        lib.CLIENT_GetLastError.restype = c_uint
        lib.CLIENT_LoginEx2.argtypes = [
            c_char_p, c_ushort, c_char_p, c_char_p, c_int, c_void_p,
            POINTER(NET_DEVICEINFO_Ex), POINTER(c_int),
        ]
        lib.CLIENT_LoginEx2.restype = c_long
        lib.CLIENT_Logout.argtypes = [c_long]
        lib.CLIENT_Logout.restype = c_int
        lib.CLIENT_QueryDevState.argtypes = [c_long, c_int, c_void_p, c_int, POINTER(c_int), c_int]
        lib.CLIENT_QueryDevState.restype = c_int
        lib.CLIENT_GetDevProtocolType.argtypes = [c_long, POINTER(c_int)]
        lib.CLIENT_GetDevProtocolType.restype = c_int
        lib.CLIENT_SetDeviceMode.argtypes = [c_long, c_int, c_void_p]
        lib.CLIENT_SetDeviceMode.restype = c_int
        lib.CLIENT_StartTalkEx.restype = c_long
        lib.CLIENT_TalkSendData.argtypes = [c_long, c_void_p, c_uint]
        lib.CLIENT_TalkSendData.restype = c_int
        lib.CLIENT_StopTalkEx.argtypes = [c_long]
        lib.CLIENT_StopTalkEx.restype = c_int
        lib.CLIENT_RecordStartEx.argtypes = [c_long]
        lib.CLIENT_RecordStartEx.restype = c_int
        lib.CLIENT_RecordStopEx.argtypes = [c_long]
        lib.CLIENT_RecordStopEx.restype = c_int
        lib.CLIENT_RecordStart.argtypes = []
        lib.CLIENT_RecordStart.restype = c_int
        lib.CLIENT_RecordStop.argtypes = []
        lib.CLIENT_RecordStop.restype = c_int

    def last_error(self) -> int:
        return int(self.lib.CLIENT_GetLastError() or 0)

    def login(self, host: str, port: int, username: str, password: str) -> LoginResult:
        info = NET_DEVICEINFO_Ex()
        error = c_int(0)
        handle = int(self.lib.CLIENT_LoginEx2(
            str(host).encode("utf-8"), int(port), str(username).encode("utf-8"),
            str(password).encode("utf-8"), EM_LOGIN_SPEC_CAP_TCP, None,
            byref(info), byref(error),
        ) or 0)
        if not handle:
            return LoginResult(0, int(port), error_code=int(error.value or self.last_error()))
        raw_serial = bytes(info.sSerialNumber).split(b"\0", 1)[0]
        return LoginResult(
            handle=handle,
            port=int(port),
            channels=max(0, int(info.nChanNum)),
            serial=raw_serial.decode("utf-8", "replace"),
            error_code=0,
        )

    def logout(self, handle: int) -> None:
        if handle:
            self.lib.CLIENT_Logout(int(handle))

    def query_talk_formats(self, login_handle: int, timeout_ms: int = 1500) -> list[TalkFormat]:
        formats = DHDEV_TALKFORMAT_LIST()
        ret_len = c_int(0)
        ok = bool(self.lib.CLIENT_QueryDevState(
            int(login_handle), DH_DEVSTATE_TALK_ECTYPE, byref(formats), sizeof(formats),
            byref(ret_len), max(500, int(timeout_ms)),
        ))
        if not ok:
            return []
        out: list[TalkFormat] = []
        count = max(0, min(int(formats.nSupportNum), 64))
        for idx in range(count):
            item = formats.type[idx]
            out.append(TalkFormat(
                encode_type=int(item.encodeType),
                sample_rate=int(item.dwSampleRate),
                audio_bits=int(item.nAudioBit),
                packet_period_ms=int(item.nPacketPeriod),
            ))
        return out

    def get_protocol_type(self, login_handle: int) -> int:
        value = c_int(EM_DEV_PROTOCOL_UNKNOWN)
        try:
            ok = bool(self.lib.CLIENT_GetDevProtocolType(int(login_handle), byref(value)))
        except Exception:
            return EM_DEV_PROTOCOL_UNKNOWN
        return int(value.value) if ok else EM_DEV_PROTOCOL_UNKNOWN

    @staticmethod
    def choose_talk_format(formats: list[TalkFormat]) -> TalkFormat:
        # Prefer the codec that field evidence already proves the iMX C family
        # understands. PCM is the vendor manual's generic fallback.
        # The official Linux 05.Talk demo configures PCM/8 kHz/16 bit in
        # server mode and pushes framed blocks through CLIENT_TalkSendData.
        # Prefer that documented sample path before codec-specific fallbacks.
        for codec in (DH_TALK_PCM, DH_TALK_G711A, DH_TALK_DEFAULT, DH_TALK_G711U):
            for item in formats:
                if item.encode_type == codec and (item.sample_rate in {0, 8000, 16000}):
                    rate = item.sample_rate or 8000
                    bits = item.audio_bits or (8 if codec in {DH_TALK_G711A, DH_TALK_G711U} else 16)
                    return TalkFormat(codec, rate, bits, item.packet_period_ms or 25)
        if formats:
            item = formats[0]
            return TalkFormat(item.encode_type, item.sample_rate or 8000, item.audio_bits or 16, item.packet_period_ms or 25)
        return TalkFormat(DH_TALK_PCM, 8000, 16, 25)

    def configure_direct_talk(
        self,
        login_handle: int,
        talk_format: TalkFormat,
        channel_index: int = 0,
        *,
        mode: str = "server",
        protocol_type: int = EM_DEV_PROTOCOL_UNKNOWN,
        audio_port: int = 0,
        speaker_channel: int = 0,
        enable_wait: bool = False,
        transfer: bool = False,
        step_callback=None,
    ) -> tuple[bool, str]:
        """Configure a direct NetSDK talk session.

        The server-mode path intentionally mirrors the official Linux 05.Talk
        demo.  In particular, an explicit packet period of 0 is preserved: the
        vendor sample zeroes DHDEV_TALKDECODE_INFO and never assigns
        nPacketPeriod.  ``step_callback`` receives one human-readable result for
        every CLIENT_SetDeviceMode call so field diagnostics can prove exactly
        which setup stage the device accepted.
        """

        def emit(name: str, ok: bool, detail: str = "") -> None:
            if step_callback is None:
                return
            state = "OK" if ok else f"FALHOU 0x{self.last_error():08x}"
            text = f"{name} • {state}"
            if detail:
                text += f" • {detail}"
            try:
                step_callback(text)
            except Exception:
                pass

        fmt = DHDEV_TALKDECODE_INFO()
        fmt.encodeType = int(talk_format.encode_type)
        fmt.dwSampleRate = int(talk_format.sample_rate or 8000)
        fmt.nAudioBit = int(talk_format.audio_bits or 16)
        # Do not use ``or`` here: zero is meaningful and is exactly what the
        # official 05.Talk sample sends after memset().
        fmt.nPacketPeriod = int(talk_format.packet_period_ms)
        ok = bool(self.lib.CLIENT_SetDeviceMode(int(login_handle), DH_TALK_ENCODE_TYPE, byref(fmt)))
        emit(
            "ENCODE_TYPE", ok,
            f"{talk_format.name} {fmt.dwSampleRate} Hz • {fmt.nAudioBit} bit • packetPeriod={fmt.nPacketPeriod}",
        )
        if not ok:
            return False, f"codec recusado (0x{self.last_error():08x})"

        normalized_mode = str(mode or "server").strip().lower()
        if normalized_mode == "v3":
            ok = bool(self.lib.CLIENT_SetDeviceMode(int(login_handle), DH_TALK_CLIENT_MODE, None))
            emit("CLIENT_MODE", ok)
            if not ok:
                return False, f"modo cliente V3 recusado (0x{self.last_error():08x})"
            talk = NET_TALK_EX()
            talk.dwSize = sizeof(NET_TALK_EX)
            talk.nChannel = max(0, int(channel_index))
            talk.nAudioPort = max(0, int(audio_port))
            talk.nWaitTime = 5000
            ok = bool(self.lib.CLIENT_SetDeviceMode(int(login_handle), DH_TALK_MODE3, byref(talk)))
            emit("MODE3", ok, f"channel={talk.nChannel} • audioPort={talk.nAudioPort} • wait={talk.nWaitTime}ms")
            if not ok:
                return False, f"parâmetros MODE3 recusados (0x{self.last_error():08x})"
        else:
            ok = bool(self.lib.CLIENT_SetDeviceMode(int(login_handle), DH_TALK_SERVER_MODE, None))
            emit("SERVER_MODE", ok)
            if not ok:
                return False, f"modo servidor de talk recusado (0x{self.last_error():08x})"

            speak = NET_SPEAK_PARAM()
            speak.dwSize = sizeof(NET_SPEAK_PARAM)
            speak.nMode = 0
            speak.nSpeakerChannel = max(0, int(speaker_channel))
            speak.bEnableWait = 1 if enable_wait else 0
            ok = bool(self.lib.CLIENT_SetDeviceMode(int(login_handle), DH_TALK_SPEAK_PARAM, byref(speak)))
            emit(
                "SPEAK_PARAM", ok,
                f"mode={speak.nMode} • speaker={speak.nSpeakerChannel} • wait={'true' if speak.bEnableWait else 'false'}",
            )
            if not ok:
                return False, f"parâmetros de speaker recusados (0x{self.last_error():08x})"

        transfer_param = NET_TALK_TRANSFER_PARAM()
        transfer_param.dwSize = sizeof(NET_TALK_TRANSFER_PARAM)
        transfer_param.bTransfer = 1 if transfer else 0
        ok = bool(self.lib.CLIENT_SetDeviceMode(int(login_handle), DH_TALK_TRANSFER_MODE, byref(transfer_param)))
        emit("TRANSFER_MODE", ok, f"transfer={'true' if transfer_param.bTransfer else 'false'}")
        if not ok:
            return False, f"modo direto recusado (0x{self.last_error():08x})"

        ch = c_int(max(0, int(channel_index)))
        ok = bool(self.lib.CLIENT_SetDeviceMode(int(login_handle), DH_TALK_TALK_CHANNEL, byref(ch)))
        emit("TALK_CHANNEL", ok, f"channel={ch.value}")
        if not ok:
            return False, f"canal de talk recusado (0x{self.last_error():08x})"

        protocol_name = {EM_DEV_PROTOCOL_V2: "V2", EM_DEV_PROTOCOL_V3: "V3"}.get(protocol_type, "desconhecido")
        return True, (
            f"OK • {normalized_mode} • protocolo {protocol_name} • "
            f"speaker={max(0, int(speaker_channel))} • wait={'true' if enable_wait else 'false'}"
        )


__all__ = [
    "IntelbrasNetSDK", "NetSDKUnavailable", "NetSDKError", "TalkFormat",
    "LoginResult", "runtime_info", "vendor_directory", "vendor_install_directory",
    "reference_audio_path", "install_from_official_archive",
    "EM_DEV_PROTOCOL_UNKNOWN", "EM_DEV_PROTOCOL_V2", "EM_DEV_PROTOCOL_V3",
]

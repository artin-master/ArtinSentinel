#!/usr/bin/env python3
"""Isolated Intelbras NetSDK worker; stdlib only. ABI: Linux NetSDK 3.050."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import queue
import select
import shutil
import signal
import socket
import array
import subprocess
import sys
import tempfile
import threading
import time

VERSION = "2.1"
HOST = "127.0.0.1"


class DeviceInfo(ctypes.Structure):
    _fields_ = [
        ("serial", ctypes.c_ubyte * 48),
        ("alarm_in", ctypes.c_int), ("alarm_out", ctypes.c_int),
        ("disks", ctypes.c_int), ("device_type", ctypes.c_int),
        ("channels", ctypes.c_int),
        ("limit_time", ctypes.c_ubyte), ("remaining", ctypes.c_ubyte),
        ("reserved_align", ctypes.c_ubyte * 2),
        ("lock_time", ctypes.c_int), ("reserved", ctypes.c_char * 24),
    ]


def validate_request(sdk_dir, port, mode, username, password):
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise ValueError("Este teste exige Linux x86-64.")
    if ctypes.sizeof(ctypes.c_long) != 8 or ctypes.sizeof(DeviceInfo) != 100 or DeviceInfo.channels.offset != 64:
        raise ValueError("ABI diferente do header Linux fornecido.")
    if not 1 <= port <= 65535 or mode not in {0,19}:
        raise ValueError("Porta ou modo inválido.")
    for text in (username, password):
        if not isinstance(text, str) or not text or "\x00" in text or len(text.encode("utf-8")) > 1024:
            raise ValueError("Credencial vazia, inválida ou longa demais; valor omitido.")
    root = Path(sdk_dir).expanduser().resolve()
    with (root / "libdhnetsdk.so").open("rb") as stream:
        elf = stream.read(20)
    if len(elf) < 20 or elf[:6] != b"\x7fELF\x02\x01" or int.from_bytes(elf[18:20], "little") != 62:
        raise ValueError("A biblioteca selecionada não é ELF x86-64 little-endian.")
    return root


def _event(fd, stage, **values):
    data = (json.dumps({"stage": stage, **values}, separators=(",", ":")) + "\n").encode()
    while data:
        written = os.write(fd, data)
        if written <= 0:
            raise OSError("Canal de eventos fechado")
        data = data[written:]


class NetTime(ctypes.Structure):
    _fields_=[(key,ctypes.c_uint) for key in ('year','month','day','hour','minute','second')]

    @classmethod
    def parse(cls,value):
        from datetime import datetime
        stamp=datetime.fromisoformat(value)
        if stamp.tzinfo is not None:raise ValueError('Use horário local do DVR.')
        return cls(stamp.year,stamp.month,stamp.day,stamp.hour,stamp.minute,stamp.second)

    def text(self):
        from datetime import datetime
        return datetime(self.year,self.month,self.day,self.hour,self.minute,self.second).isoformat()


class RecordInfo(ctypes.Structure):
    _fields_=[('channel',ctypes.c_uint),('filename',ctypes.c_char*124),
              ('frames',ctypes.c_uint),('size',ctypes.c_uint),('start',NetTime),('end',NetTime),
              ('drive',ctypes.c_uint),('cluster',ctypes.c_uint),('kind',ctypes.c_ubyte),
              ('important',ctypes.c_ubyte),('hint',ctypes.c_ubyte),('stream',ctypes.c_ubyte)]


def _records(lib,login,event_fd,options):
    if ctypes.sizeof(NetTime)!=24 or ctypes.sizeof(RecordInfo)!=196:raise ValueError('ABI de gravação inválida.')
    begin,end=NetTime.parse(options['start']),NetTime.parse(options['end'])
    if end.text()<=begin.text():raise ValueError('Período inválido.')
    channel=int(options['channel'])
    if not 1<=channel<=256:raise ValueError('Canal inválido.')
    lib.CLIENT_QueryRecordFile.argtypes=[ctypes.c_long,ctypes.c_int,ctypes.c_int,ctypes.POINTER(NetTime),ctypes.POINTER(NetTime),ctypes.c_char_p,ctypes.POINTER(RecordInfo),ctypes.c_int,ctypes.POINTER(ctypes.c_int),ctypes.c_int,ctypes.c_int]
    lib.CLIENT_QueryRecordFile.restype=ctypes.c_int
    files=(RecordInfo*300)();count=ctypes.c_int()
    if not lib.CLIENT_QueryRecordFile(login,channel-1,0,ctypes.byref(begin),ctypes.byref(end),None,files,ctypes.sizeof(files),ctypes.byref(count),5000,0):
        _event(event_fd,'record_search_failed',sdk_error=int(lib.CLIENT_GetLastError()));return 15
    if not 0<=count.value<=300:raise ValueError('Contagem inválida.')
    items=[]
    for value in files[:count.value]:
        try:begin_text,end_text=value.start.text(),value.end.text()
        except ValueError:continue
        # No filename/path, serial or account values are emitted.
        items.append(dict(channel=int(value.channel)+1,start=begin_text,end=end_text,size=int(value.size)*1024,kind={0:'Normal',1:'Alarme',2:'Movimento'}.get(value.kind,'Outro')))
    _event(event_fd,'recordings',items=items,truncated=count.value==300)
    return 0


def _preview(lib, login, event_fd, options, control=None):
    """Raw callback contract from dhnetsdk.h; no guessed YUV/frame structures."""
    callback_type = ctypes.CFUNCTYPE(None, ctypes.c_long, ctypes.c_uint,
        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint, ctypes.c_long, ctypes.c_long)
    lib.CLIENT_RealPlayEx.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
    lib.CLIENT_RealPlayEx.restype = ctypes.c_long
    lib.CLIENT_SetRealDataCallBackEx2.argtypes = [ctypes.c_long, callback_type, ctypes.c_long, ctypes.c_uint]
    lib.CLIENT_SetRealDataCallBackEx2.restype = ctypes.c_int
    lib.CLIENT_StopRealPlayEx.argtypes = [ctypes.c_long]
    lib.CLIENT_StopRealPlayEx.restype = ctypes.c_int
    media_fd = int(options["media_fd"])
    os.set_blocking(media_fd, False)
    # Packet count alone prematurely rejects short bursts of small chunks.
    # Bound both the remaining payload bytes and the number of queued objects.
    pending = queue.Queue(maxsize=2048)
    budget = 8 * 1024 * 1024
    failed, draining = threading.Event(), threading.Event()
    discarding = threading.Event()
    counts = {"bytes": 0, "packets": 0, "written": 0, "buffer_peak": 0}
    flow = {"buffered": 0, "reason": "", "errno": 0}
    lock = threading.RLock()
    generation=0
    transitioning=threading.Event()

    def fail(reason, number=0):
        with lock:
            if not flow["reason"]:
                flow["reason"], flow["errno"] = reason, int(number or 0)
            failed.set()

    def receive(real, data_type, buffer, length, param, user):
        try:
            if data_type != 0 or not buffer or not length or failed.is_set() or draining.is_set() or transitioning.is_set():
                return
            if length > 4 * 1024 * 1024:
                fail("packet_size_limit")
                return
            with lock:
                if flow["buffered"] + length > budget or pending.full():
                    fail("buffer_capacity")
                    return
                if transitioning.is_set():return
                data = ctypes.string_at(buffer, length)
                pending.put_nowait(data)
                flow["buffered"] += length
                counts["buffer_peak"] = max(counts["buffer_peak"], flow["buffered"])
                counts["bytes"] += length
                counts["packets"] += 1
        except Exception as exc:
            fail("callback_" + type(exc).__name__, getattr(exc, "errno", 0))

    def send():
        try:
            while not failed.is_set() and not discarding.is_set():
                with lock:
                    try:data=memoryview(pending.get_nowait());epoch=generation
                    except queue.Empty:data=None
                if data is None:
                    if draining.is_set():return
                    time.sleep(.01);continue
                while data and not failed.is_set() and not discarding.is_set():
                    with lock:
                        if epoch!=generation:break
                        target_fd=media_fd
                    try:ready=select.select([],[target_fd],[],.05)[1]
                    except (OSError,ValueError):
                        with lock:
                            if epoch!=generation:break
                        raise
                    if not ready:continue
                    with lock:
                        if epoch!=generation:break
                        try:size=os.write(media_fd,data)
                        except BlockingIOError:continue
                        if size<=0:fail('pipe_no_progress');return
                        counts['written']+=size;flow['buffered']-=size;data=data[size:]

        except Exception as exc:
            fail('sender_'+type(exc).__name__,getattr(exc,'errno',0))

    def retarget(real):
        nonlocal media_fd,generation
        raw,ancillary,flags,_=control.recvmsg(8192,socket.CMSG_SPACE(array.array('i').itemsize))
        descriptors=array.array('i')
        for level,kind,data in ancillary:
            if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                descriptors.frombytes(data[:len(data)-len(data)%descriptors.itemsize])
        ident=0
        try:
            command=json.loads(raw);ident=int(command.get('id',0))
            if flags & (socket.MSG_TRUNC|socket.MSG_CTRUNC) or len(descriptors)!=1 or set(command)!={'action','at','speed','id'} or command['action']!='retarget':raise ValueError('command')
            target=NetTime.parse(command['at']);speed=float(command['speed'])
            from datetime import datetime
            moment=datetime.fromisoformat(command['at'])
            first,last=(datetime.fromisoformat(options['playback'][k]) for k in ('start','end'))
            if not first<=moment<last or speed not in (0.5,1,2,4,8,16):raise ValueError('window_speed')
            if not hasattr(lib,'CLIENT_SeekPlayBackByTime'):raise ValueError('seek_unavailable')
            os.set_blocking(descriptors[0],False)
            lib.CLIENT_SeekPlayBackByTime.argtypes=[ctypes.c_long,ctypes.POINTER(NetTime)]
            lib.CLIENT_SeekPlayBackByTime.restype=ctypes.c_int
            lib.CLIENT_SetPlayBackSpeed.argtypes=[ctypes.c_long,ctypes.c_int]
            lib.CLIENT_SetPlayBackSpeed.restype=ctypes.c_int
            transitioning.set()
            if not lib.CLIENT_PausePlayBack(real,1):raise ValueError('pause_failed')
            # No old queued bytes may enter the replacement decoder.
            with lock:
                generation+=1
                while not pending.empty():pending.get_nowait()
                flow['buffered']=0
                old=media_fd;media_fd=descriptors.pop();options['media_fd']=media_fd
                os.close(old)
            if not lib.CLIENT_SeekPlayBackByTime(real,ctypes.byref(target)):raise ValueError('seek_rejected')
            if not lib.CLIENT_SetPlayBackSpeed(real,{.5:-1,1:0,2:1,4:2,8:3,16:4}[speed]):raise ValueError('speed_rejected')
            transitioning.clear()
            if not lib.CLIENT_PausePlayBack(real,0):raise ValueError('resume_failed')
            _event(event_fd,'playback_retargeted',id=ident,speed=speed)
            return True
        except (ValueError,KeyError,TypeError,OverflowError):
            _event(event_fd,'playback_retarget_failed',id=ident)
            fail('retarget_failed')
            return False
        finally:
            for fd in descriptors:os.close(fd)


    real = 0
    stop_confirmed = False
    lib._as_preview_clean = False
    sender = threading.Thread(target=send, daemon=True)
    callback = callback_type(receive)  # Remains alive through StopRealPlayEx.
    # A failed Stop may leave callbacks in flight until CLIENT_Cleanup returns.
    # Keep the C trampoline and its Python closure owned by the worker's CDLL.
    lib._as_preview_callback = callback
    sender.start()
    code = 11
    try:
        if 'playback' in options:
            playback_type=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_long,ctypes.c_uint,ctypes.POINTER(ctypes.c_ubyte),ctypes.c_uint,ctypes.c_long)
            def playback_receive(handle,kind,data,length,user):
                receive(handle,kind,data,length,0,user)
                return 0 if failed.is_set() else 1
            callback=playback_type(playback_receive)
            lib._as_preview_callback=callback
            begin,end=(NetTime.parse(options['playback'][key]) for key in ('start','end'))
            lib.CLIENT_PlayBackByTimeEx.argtypes=[ctypes.c_long,ctypes.c_int,ctypes.POINTER(NetTime),ctypes.POINTER(NetTime),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_long,playback_type,ctypes.c_long]
            lib.CLIENT_PlayBackByTimeEx.restype=ctypes.c_long
            lib.CLIENT_StopPlayBack.argtypes=[ctypes.c_long];lib.CLIENT_StopPlayBack.restype=ctypes.c_int
            real=int(lib.CLIENT_PlayBackByTimeEx(login,int(options['channel'])-1,ctypes.byref(begin),ctypes.byref(end),None,None,0,callback,0) or 0)
        else:
            # Header: main stream = 2; extra stream 1 = 3; SDK channel is zero-based.
            real = int(lib.CLIENT_RealPlayEx(login, int(options["channel"]) - 1, None,
                                            2 if options["stream"] == "main" else 3) or 0)
        if not real:
            _event(event_fd, "stream_open_failed", sdk_error=int(lib.CLIENT_GetLastError()))
            return 11
        if 'playback' not in options and not lib.CLIENT_SetRealDataCallBackEx2(real, callback, 0, 1):
            _event(event_fd, "callback_failed", sdk_error=int(lib.CLIENT_GetLastError()))
            return 12
        if 'playback' in options:
            speed=float(options.get('playback_speed',1))
            mapping={0.5:-1,1:0,2:1,4:2,8:3,16:4}
            if speed not in mapping:raise ValueError('Velocidade inválida.')
            if speed!=1:
                lib.CLIENT_SetPlayBackSpeed.argtypes=[ctypes.c_long,ctypes.c_int]
                lib.CLIENT_SetPlayBackSpeed.restype=ctypes.c_int
                if not lib.CLIENT_SetPlayBackSpeed(real,mapping[speed]):
                    _event(event_fd,'playback_speed_failed',requested=speed,sdk_error=int(lib.CLIENT_GetLastError()))
                    return 16
            _event(event_fd,'playback_speed_applied',speed=speed)
        _event(event_fd, "stream_started", channel=int(options["channel"]), stream=options["stream"],native_seek=bool('playback' in options and hasattr(lib,'CLIENT_SeekPlayBackByTime')))
        announced = False
        last_report = 0.0
        paused=False
        if 'playback' in options:
            lib.CLIENT_PausePlayBack.argtypes=[ctypes.c_long,ctypes.c_int]
            lib.CLIENT_PausePlayBack.restype=ctypes.c_int
        while not failed.is_set():
            if select.select([int(options["cancel_fd"])], [], [], 0.02)[0]:
                break
            if control is not None and select.select([control],[],[],0)[0]:
                if not retarget(real):break
                paused=False
            if 'playback' in options:
                with lock:
                    buffered=flow['buffered']
                    queued=pending.qsize()
                target=True if (buffered>budget//2 or queued>pending.maxsize//2) else False if (buffered<budget//4 and queued<pending.maxsize//4) else paused
                if target!=paused:
                    if not lib.CLIENT_PausePlayBack(real,int(target)):
                        fail('playback_flow_control_failed');break
                    paused=target
                    _event(event_fd,'playback_flow_paused' if paused else 'playback_flow_resumed',buffered=buffered,queued=queued)
            if options.get('report_progress') and time.monotonic()-last_report >= 1:
                with lock:
                    snapshot = dict(counts, buffered=flow['buffered'], queued=pending.qsize(), paused=paused)
                _event(event_fd, 'stream_progress', **snapshot)
                last_report = time.monotonic()
            if counts["bytes"] and not announced:
                _event(event_fd, "stream_data_received")
                announced = True
            time.sleep(0.02)
        code = 14 if failed.is_set() else (0 if counts["bytes"] else 13)
    finally:
        if real:
            stop=lib.CLIENT_StopPlayBack if 'playback' in options else lib.CLIENT_StopRealPlayEx
            if stop(real):
                stop_confirmed = True
                _event(event_fd, "stream_stopped")
            else:
                _event(event_fd, "stream_stop_failed", sdk_error=int(lib.CLIENT_GetLastError()))
                code = 8
        draining.set()
        if options.get('discard_on_stop'):discarding.set()
        sender.join(timeout=3)
        if sender.is_alive():
            fail("drain_timeout")
            sender.join(timeout=1)
            code = 14
        if failed.is_set() and code == 0:
            code = 14
        if flow["reason"]:
            _event(event_fd, "stream_error", reason=flow["reason"], errno=flow["errno"])
        _event(event_fd, "stream_summary", **counts)
        lib._as_preview_clean = stop_confirmed and not sender.is_alive() and not failed.is_set()
    return code


def _persistent_operations(lib, login, event_fd, options, control_fd, channels):
    """Sequential queries OR playback; their logins are pooled separately."""
    with socket.socket(fileno=control_fd) as control:
        while True:
            if 'record_query' in options:
                query=options['record_query']
                if not 1 <= int(query['channel']) <= 256:
                    raise ValueError('Canal inválido.')
                for key in ('start','end'):NetTime.parse(query[key])
                from datetime import datetime
                start,finish=(datetime.fromisoformat(query[key]) for key in ('start','end'))
                if finish<=start or (finish-start).total_seconds()>86400:raise ValueError('Período inválido.')
                code=_records(lib,login,event_fd,query)
                if code:return code
            else:
                try:
                    if not 1 <= int(options['channel']) <= channels:
                        raise ValueError('Canal inválido.')
                    if options.get('playback_speed',1) not in (0.5,1,2,4,8,16):
                        raise ValueError('Velocidade inválida.')
                    for value in options['playback'].values():NetTime.parse(value)
                    options['discard_on_stop']=True
                    code=_preview(lib,login,event_fd,options,control=control)
                finally:
                    os.close(options['media_fd']);os.close(options['cancel_fd'])
                if code not in (0,13,16) or not lib._as_preview_clean:return code or 8
            _event(event_fd,'session_idle')
            if not select.select([control],[],[],60)[0]:return 0
            raw,ancillary,flags,_=control.recvmsg(8192,socket.CMSG_SPACE(2*array.array('i').itemsize))
            if not raw:return 0
            descriptors=array.array('i')
            for level,kind,data in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                    descriptors.frombytes(data[:len(data)-len(data)%descriptors.itemsize])
            try:
                if flags & (socket.MSG_TRUNC|socket.MSG_CTRUNC):
                    raise ValueError('Controle inválido.')
                options=json.loads(raw)
                if set(options)=={'record_query'} and len(descriptors)==0:
                    pass
                elif set(options)=={'channel','stream','playback','playback_speed'} and len(descriptors)==2:
                    options.update(media_fd=descriptors[0],cancel_fd=descriptors[1])
                else:raise ValueError('Operação inválida.')
            except Exception:
                for fd in descriptors:os.close(fd)
                raise
            _event(event_fd,'session_reused')


def _worker(event_fd):
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    lib = None
    initialized = False
    handle = 0
    code = 3
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise ValueError("Configuração grande demais")
        request = json.loads(raw)
        host=request.get('host',HOST)
        if request['mode']==19 and host!=HOST:raise ValueError('Cloud exige loopback.')
        if not isinstance(host,str) or not host or any(c.isspace() for c in host) or any(c in host for c in '/@\\'):raise ValueError('Destino inválido.')
        if request.get('video',{}).get('playback_speed',1) not in (0.5,1,2,4,8,16):raise ValueError('Velocidade inválida.')
        root = validate_request(request["sdk_dir"], request["port"], request["mode"],
                                request["username"], request["password"])
        _event(event_fd, "worker_started", abi_info=ctypes.sizeof(DeviceInfo),
               abi_handle=ctypes.sizeof(ctypes.c_long))
        peers = []  # Retain handles until process shutdown, same order as AS.
        for name in ("libInfra.so", "libStream.so", "libNetFramework.so",
                     "libdhconfigsdk.so", "libavnetsdk.so", "libStreamSvr.so"):
            path = root / name
            if path.is_file():
                try:
                    peers.append(ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL))
                except OSError:
                    _event(event_fd, "preload_warning", library=name)
        lib = ctypes.CDLL(str(root / "libdhnetsdk.so"), mode=ctypes.RTLD_GLOBAL)
        signatures = {
            "CLIENT_Init": ([ctypes.c_void_p, ctypes.c_long], ctypes.c_int),
            "CLIENT_SetConnectTime": ([ctypes.c_int, ctypes.c_int], None),
            "CLIENT_GetLastError": ([], ctypes.c_uint),
            "CLIENT_GetSDKVersion": ([], ctypes.c_uint),
            "CLIENT_LoginEx2": ([ctypes.c_char_p, ctypes.c_ushort,
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p,
                ctypes.POINTER(DeviceInfo), ctypes.POINTER(ctypes.c_int)], ctypes.c_long),
            "CLIENT_Logout": ([ctypes.c_long], ctypes.c_int),
            "CLIENT_Cleanup": ([], None),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(lib, name)
            function.argtypes = arguments
            function.restype = result
        _event(event_fd, "sdk_loaded", version=int(lib.CLIENT_GetSDKVersion()))
        if not lib.CLIENT_Init(None, 0):
            _event(event_fd, "init_failed", sdk_error=int(lib.CLIENT_GetLastError()))
            return 4
        initialized = True
        lib.CLIENT_SetConnectTime(8000, 1)
        info, error = DeviceInfo(), ctypes.c_int(0)
        _event(event_fd, "login_started", mode=request["mode"], port=request["port"])
        # Exactly one call. Never substitute another mode or retry credentials.
        handle = int(lib.CLIENT_LoginEx2(host.encode("ascii"), request["port"],
            request["username"].encode("utf-8"), request["password"].encode("utf-8"),
            request["mode"], None, ctypes.byref(info), ctypes.byref(error)) or 0)
        if not handle:
            _event(event_fd, "login_failed", login_error=int(error.value),
                   sdk_error=int(lib.CLIENT_GetLastError()))
            code = 5
        else:
            serial = bytes(info.serial).split(b"\0", 1)[0].decode("ascii").strip().upper()
            if request["expected_serial"] and serial != request["expected_serial"]:
                _event(event_fd, "identity_mismatch")
                code = 9
            elif not 1 <= int(info.channels) <= 256:
                _event(event_fd, "inventory_invalid")
                code = 9
            else:
                _event(event_fd, "login_ok", channels=int(info.channels), serial_verified=bool(request["expected_serial"]),mode=request["mode"])
                if "video" in request and not 1 <= int(request["video"]["channel"]) <= int(info.channels):
                    _event(event_fd, "channel_invalid")
                    code = 11
                else:
                    code = (_persistent_operations(lib,handle,event_fd,{'record_query':request['record_query']} if 'record_query' in request else request['video'],request['control_fd'],int(info.channels)) if 'control_fd' in request
                            else _records(lib,handle,event_fd,request["record_query"]) if "record_query" in request
                            else _preview(lib, handle, event_fd, request["video"]) if "video" in request else 0)
    except Exception as exc:
        # Exception text could contain data from an argument; report type only.
        _event(event_fd, "worker_exception", error_type=type(exc).__name__)
        code = 3
    finally:
        if initialized:
            try:
                if handle:
                    if lib.CLIENT_Logout(handle):
                        _event(event_fd, "logout_ok")
                    else:
                        _event(event_fd, "logout_failed", sdk_error=int(lib.CLIENT_GetLastError()))
                        code = 8
                _event(event_fd, "cleanup_started")
                lib.CLIENT_Cleanup()
                _event(event_fd, "cleanup_returned")
            except Exception as exc:
                _event(event_fd, "cleanup_exception", error_type=type(exc).__name__)
                code = 8
    return code



if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        raise SystemExit(2)
    raise SystemExit(_worker(int(sys.argv[2])))

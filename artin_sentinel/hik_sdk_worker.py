"""Private stdlib-only native worker; credentials arrive exclusively by stdin pipe."""
import ctypes as C
from datetime import datetime
import ipaddress
import json
import os
from pathlib import Path
import queue
import resource
import select
import struct
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from artin_sentinel.hik_sdk_abi import NET_DVR_USER_LOGIN_INFO,NET_DVR_DEVICEINFO_V40,NET_DVR_PREVIEWINFO
from artin_sentinel.hik_sdk_layout import PLAYBACK as ABI

CALLBACK=C.CFUNCTYPE(None,C.c_int32,C.c_uint32,C.POINTER(C.c_ubyte),C.c_uint32,C.c_void_p)

def bind(sdk,name,args,ret=C.c_int):
    function=getattr(sdk,name);function.argtypes=args;function.restype=ret;return function

def apply_speed(control,handle,speed):
    """HCNetSDK.h: PLAYNORMAL=7, PLAYFAST=5, PLAYSLOW=6."""
    if speed not in (0.5,1,2,4,8):raise ValueError('speed')
    if not control(handle,7,None,0,None,None):return False
    commands={0.5:[6],1:[],2:[5],4:[5,5],8:[5,5,5]}[speed]
    return all(control(handle,command,None,0,None,None) for command in commands)

def media(sdk,user,request,emit):
    cancel=request['cancel_fd'];fd=request['media_fd'];playback='start' in request
    packets=queue.Queue(maxsize=4096);lock=threading.Lock();stop=threading.Event();failure=threading.Event()
    accepting=threading.Event();accepting.set()
    stats={'bytes':0,'packets':0,'queued':0,'peak':0,'sent':0};last=[time.monotonic()]
    def callback(handle,kind,buffer,size,opaque):
        if not accepting.is_set() or stop.is_set() or failure.is_set() or kind not in (1,2) or not size:return
        with lock:
            if size>1024*1024 or stats['queued']+size>8*1024*1024:
                failure.set();return
            try:packets.put_nowait(C.string_at(buffer,size))
            except queue.Full:failure.set();return
            stats['queued']+=size;stats['peak']=max(stats['peak'],stats['queued'])
            stats['bytes']+=size;stats['packets']+=1;last[0]=time.monotonic()
    cb=CALLBACK(callback)
    os.set_blocking(fd,False)
    def write():
        try:
            while not stop.is_set():
                try:data=packets.get(timeout=.1)
                except queue.Empty:continue
                with lock:stats['queued']-=len(data)
                view=memoryview(data)
                while view and not stop.is_set():
                    read,ready,_=select.select([cancel],[fd],[],.1)
                    if read:return
                    if ready:
                        try:count=os.write(fd,view)
                        except BlockingIOError:continue
                        stats['sent']+=count;view=view[count:]
        except (OSError,ValueError):failure.set()
    writer=threading.Thread(target=write,daemon=True);writer.start()
    handle=-1;paused=False;control=None;complete=False;position_supported=True;position_at=0
    try:
        if playback:
            create=bind(sdk,'NET_DVR_PlayBackByTime_V40',[C.c_int32,C.c_void_p],C.c_int32)
            close=bind(sdk,'NET_DVR_StopPlayBack',[C.c_int32])
            register=bind(sdk,'NET_DVR_SetPlayDataCallBack_V40',[C.c_int32,CALLBACK,C.c_void_p])
            control=bind(sdk,'NET_DVR_PlayBackControl_V40',[C.c_int32,C.c_uint32,C.c_void_p,C.c_uint32,C.c_void_p,C.POINTER(C.c_uint32)])
            begin,end=(datetime.fromisoformat(request[k]) for k in ('start','end'))
            if begin.tzinfo or end.tzinfo or not 0<(end-begin).total_seconds()<=86400:raise ValueError('period')
            params=C.create_string_buffer(ABI['NET_DVR_VOD_PARA.size'])
            struct.pack_into('<I',params,0,len(params));offset=ABI['NET_DVR_VOD_PARA.struIDInfo']
            struct.pack_into('<I',params,offset,ABI['NET_DVR_STREAM_INFO.size'])
            struct.pack_into('<I',params,offset+ABI['NET_DVR_STREAM_INFO.dwChannel'],request['channel'])
            for field,value in [('struBeginTime',begin),('struEndTime',end)]:
                struct.pack_into('<6I',params,ABI['NET_DVR_VOD_PARA.'+field],value.year,value.month,value.day,value.hour,value.minute,value.second)
            handle=int(create(user,params))
            if handle<0:emit('error',code=int(sdk.NET_DVR_GetLastError()),operation='playback_open');return
            if not register(handle,cb,None) or not control(handle,1,None,0,None,None):
                emit('error',code=int(sdk.NET_DVR_GetLastError()),operation='playback_start');return
            speed=float(request.get('speed',1))
            if speed!=1 and not apply_speed(control,handle,speed):
                emit('error',operation='playback_speed_rejected',code=int(sdk.NET_DVR_GetLastError()));return
            emit('speed_accepted',speed=speed)
        else:
            create=bind(sdk,'NET_DVR_RealPlay_V40',[C.c_int32,C.POINTER(NET_DVR_PREVIEWINFO),CALLBACK,C.c_void_p],C.c_int32)
            close=bind(sdk,'NET_DVR_StopRealPlay',[C.c_int32])
            params=NET_DVR_PREVIEWINFO();params.lChannel=request['channel'];params.bBlocked=1;params.dwDisplayBufNum=1
            params.dwStreamType=1 if request.get('stream')=='sub' else 0
            handle=int(create(user,C.byref(params),cb,None))
            if handle<0:emit('error',code=int(sdk.NET_DVR_GetLastError()),operation='live_open');return
        emit('stream_started',playback=playback)
        while not select.select([cancel],[],[],.05)[0]:
            if failure.is_set():emit('error',operation='media_queue_or_pipe');break
            if not paused and time.monotonic()-last[0]>20:
                emit('error',operation='no_media_timeout');break
            if playback and control is not None:
                if position_supported and time.monotonic()>=position_at:
                    position_at=time.monotonic()+1
                    position=C.c_uint32();returned=C.c_uint32()
                    if control(handle,13,None,0,C.byref(position),C.byref(returned)) and returned.value==4:
                        if position.value==100:
                            if stats['bytes']:complete=True
                            else:emit('error',operation='playback_completed_without_media')
                            break
                        if position.value>100:emit('error',operation='playback_position_error',code=position.value);break
                    else:position_supported=False
                with lock:queued=stats['queued']
                command=3 if not paused and queued>2*1024*1024 else 4 if paused and queued<512*1024 else None
                if command is not None:
                    if not control(handle,command,None,0,None,None):
                        emit('error',operation='playback_flow_control',code=int(sdk.NET_DVR_GetLastError()));break
                    paused=command==3
                    if not paused:last[0]=time.monotonic()
    finally:
        accepting.clear()
        if handle>=0:emit('stream_closed',ok=bool(close(handle)))
        if complete:
            deadline=time.monotonic()+60
            while stats['sent']<stats['bytes'] and not failure.is_set() and not select.select([cancel],[],[],.05)[0] and time.monotonic()<deadline:pass
            if stats['sent']==stats['bytes']:emit('playback_complete')
            elif not select.select([cancel],[],[],0)[0]:emit('error',operation='playback_tail_incomplete')
        stop.set()
        writer.join(timeout=.5)
        emit('media_summary',bytes=stats['bytes'],packets=stats['packets'],sent=stats['sent'],peak=stats['peak'])
        os.close(fd)

def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));event_fd=int(sys.argv[1])
    def emit(stage,**fields):
        try:
            payload=(json.dumps(dict(stage=stage,**fields))+'\n').encode()
            while payload:payload=payload[os.write(event_fd,payload):]
        except (OSError,BrokenPipeError):pass
    user=-1;initialized=False;sdk=None
    try:
        request=json.load(sys.stdin)
        ipaddress.ip_address(request['host'])
        if not 1<=int(request['port'])<=65535 or not 1<=int(request['channel'])<=256:raise ValueError('endpoint')
        sdk=C.CDLL(request['library'],mode=os.RTLD_NOW|os.RTLD_LOCAL)
        init=bind(sdk,'NET_DVR_Init',[]);cleanup=bind(sdk,'NET_DVR_Cleanup',[])
        bind(sdk,'NET_DVR_GetLastError',[],C.c_uint32)
        login=bind(sdk,'NET_DVR_Login_V40',[C.POINTER(NET_DVR_USER_LOGIN_INFO),C.POINTER(NET_DVR_DEVICEINFO_V40)],C.c_int32)
        logout=bind(sdk,'NET_DVR_Logout',[C.c_int32])
        if not init():emit('error',operation='init',code=int(sdk.NET_DVR_GetLastError()));return
        initialized=True
        if not bind(sdk,'NET_DVR_SetConnectTime',[C.c_uint32,C.c_uint32])(5000,1) or not bind(sdk,'NET_DVR_SetReconnect',[C.c_uint32,C.c_int])(30000,0):
            emit('error',operation='connection_policy');return
        info=NET_DVR_USER_LOGIN_INFO();info.sDeviceAddress=request['host'].encode('ascii');info.wPort=request['port']
        for key,field in [('username','sUserName'),('password','sPassword')]:
            value=request.pop(key).encode()
            if not 1<=len(value)<64 or b'\0' in value:raise ValueError('credential')
            setattr(info,field,value)
        device=NET_DVR_DEVICEINFO_V40()
        try:user=int(login(C.byref(info),C.byref(device)))
        finally:C.memset(C.addressof(info),0,C.sizeof(info))
        if user<0:emit('login_failed',code=int(sdk.NET_DVR_GetLastError()));return
        emit('login_ok',serial_verified=False)
        if request.get('action')=='search':
            from artin_sentinel.hik_sdk_native_search import search
            emit('search_result',result=search(sdk,user,request['start'],request['end'],request['channel']))
        else:media(sdk,user,request,emit)
    except Exception as error:emit('error',operation='worker',error_type=type(error).__name__)
    finally:
        if user>=0:emit('logout',ok=bool(logout(user)))
        if initialized:emit('cleanup',ok=bool(cleanup()))

if __name__=='__main__':main()

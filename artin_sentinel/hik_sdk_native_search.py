"""Bounded local recording index query. No file downloads or device writes."""
import ctypes as C
from datetime import date,datetime
import json
from pathlib import Path
import struct
import time

from .hik_sdk_layout import SEARCH as ABI

def search(sdk,user,start,end,channel=1,seconds=15,limit=100):
    begin,finish=datetime.fromisoformat(start),datetime.fromisoformat(end)
    if begin.tzinfo or finish.tzinfo or not 0<(finish-begin).total_seconds()<=86400 or not 1<=channel<=256:raise ValueError("invalid_search")
    result={'status':'preparing','start_device_local':start,'channel':channel,'files':[],
            'partial':False,'stream_filter':'main_preferred'}
    try:
        find=sdk.NET_DVR_FindFile_V40
        next_file=sdk.NET_DVR_FindNextFile_V40
        close=sdk.NET_DVR_FindClose_V30
    except AttributeError:
        result['status']='search_export_missing';return result
    find.argtypes=[C.c_int32,C.c_void_p];find.restype=C.c_int32
    next_file.argtypes=[C.c_int32,C.c_void_p];next_file.restype=C.c_int32
    close.argtypes=[C.c_int32];close.restype=C.c_int
    condition=C.create_string_buffer(ABI['NET_DVR_FILECOND_V40.size'])
    def put(name,value):struct.pack_into('<I',condition,ABI['NET_DVR_FILECOND_V40.'+name],value)
    put('lChannel',channel);put('dwFileType',255);put('dwIsLocked',255)
    for field,values in [('struStartTime',(begin.year,begin.month,begin.day,begin.hour,begin.minute,begin.second)),
                         ('struStopTime',(finish.year,finish.month,finish.day,finish.hour,finish.minute,finish.second))]:
        struct.pack_into('<6I',condition,ABI['NET_DVR_FILECOND_V40.'+field],*values)
    handle=int(find(user,condition))
    if handle<0:
        result.update(status='search_open_failed',sdk_error=int(sdk.NET_DVR_GetLastError()));return result
    buffer=C.create_string_buffer(ABI['NET_DVR_FINDDATA_V40.size'])
    def timestamp(field):
        values=struct.unpack_from('<6I',buffer,ABI['NET_DVR_FINDDATA_V40.'+field])
        try:return datetime(*values).isoformat()
        except ValueError:return None
    deadline=time.monotonic()+seconds
    try:
        while time.monotonic()<deadline:
            C.memset(C.addressof(buffer),0,C.sizeof(buffer))
            status=int(next_file(handle,buffer))
            result['last_search_code']=status
            if status==1000:
                row={'start':timestamp('struStartTime'),'end':timestamp('struStopTime'),
                     'size_bytes_reported':struct.unpack_from('<I',buffer,ABI['NET_DVR_FINDDATA_V40.dwFileSize'])[0],
                     'record_type_code':C.c_ubyte.from_buffer(buffer,ABI['NET_DVR_FINDDATA_V40.byFileType']).value,
                     'stream_code':C.c_ubyte.from_buffer(buffer,ABI['NET_DVR_FINDDATA_V40.byStreamType']).value}
                result['files'].append(row)
                if len(result['files'])>=limit:
                    result.update(status='result_limit',partial=True);break
            elif status==1002:
                time.sleep(min(0.1,max(0,deadline-time.monotonic())))
            elif status in (1001,1003):
                result['status']='completed' if result['files'] else 'no_files_in_requested_day';break
            else:
                result.update(status='search_failed',sdk_error=int(sdk.NET_DVR_GetLastError()),partial=True);break
        else:result.update(status='search_time_limit',partial=True)
    finally:
        C.memset(C.addressof(buffer),0,C.sizeof(buffer))
        result['search_close_ok']=bool(close(handle))
        if not result['search_close_ok']:result['close_error']=int(sdk.NET_DVR_GetLastError())
    return result

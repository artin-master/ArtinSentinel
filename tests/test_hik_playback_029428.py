from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from xml.etree import ElementTree as ET
import pytest
from artin_sentinel import recorder
from artin_sentinel.hik_recording import search_hikvision_recordings
from artin_sentinel.recording_search import RecordingSearchError

class Response:
    def __init__(self, data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return self.data

class Opener:
    def __init__(self, pages): self.pages=iter(pages); self.requests=[]
    def open(self, request, **kwargs):
        self.requests.append(request)
        return Response(next(self.pages))

def page(status='OK', n=1):
    items=''.join(f'<searchMatchItem><trackID>101</trackID><timeSpan><startTime>2026-10-21T12:{i:02d}:00Z</startTime><endTime>2026-10-21T12:{i:02d}:30Z</endTime></timeSpan><mediaSegmentDescriptor><playbackURI>rtsp://192.0.2.1/Streaming/tracks/101/?starttime=20261021T120000Z&amp;endtime=20261021T130000Z</playbackURI></mediaSegmentDescriptor></searchMatchItem>' for i in range(n))
    return f'<CMSearchResult><responseStatus>true</responseStatus><responseStatusStrg>{status}</responseStatusStrg><matchList>{items}</matchList></CMSearchResult>'.encode()

def query(opener):
    return search_hikvision_recordings('http://192.0.2.1','user','secret',1,datetime(2026,10,21),datetime(2026,10,22),opener=opener)

def test_more_continues_short_pages_with_same_search_id():
    op=Opener([page('MORE'),page('OK')]); result=query(op)
    assert len(op.requests)==2
    roots=[ET.fromstring(r.data) for r in op.requests]
    def val(root,name): return next(x.text for x in root.iter() if x.tag.split('}')[-1]==name)
    assert val(roots[0],'searchID')==val(roots[1],'searchID')
    assert val(roots[1],'searchResultPostion')=='1'
    assert len(result.recordings)==1  # duplicated result must not duplicate the timeline

def test_failed_search_is_not_an_empty_calendar():
    with pytest.raises(RecordingSearchError): query(Opener([b'<CMSearchResult><responseStatus>false</responseStatus><responseStatusStrg>ERROR</responseStatusStrg></CMSearchResult>']))

def test_unusable_segment_is_partial_evidence_not_confirmed_empty_day():
    result=query(Opener([page().replace(b'rtsp://192.0.2.1',b'http://192.0.2.1')]))
    assert not result.recordings and result.ignored==1

def test_authenticated_empty_inventory_is_not_a_bad_password(monkeypatch):
    monkeypatch.setattr(recorder,'probe_hikvision_isapi_device_info',lambda *a,**k:NS(authenticated=True,ok=True,manufacturer='Hikvision',model='DS-test',firmware='V1',detail='OK'))
    monkeypatch.setattr(recorder,'probe_hikvision_isapi_streaming_channels',lambda *a,**k:NS(stream_ids=(),physical_channels=(),detail='vazio'))
    monkeypatch.setattr(recorder,'probe_hikvision_isapi_video_inputs',lambda *a,**k:NS(inputs=(),detail='vazio'))
    monkeypatch.setattr(recorder,'probe_hikvision_input_proxy_status',lambda *a,**k:NS(channels=(),detail='vazio'))
    monkeypatch.setattr(recorder,'probe_rtsp_url_detailed',lambda *a,**k:recorder.RtspProbeReport(False,404,'sem stream'))
    rows=recorder.scan_hikvision_channels('192.0.2.1','u','p',max_channels=1)
    assert rows==[] and rows.preserve_existing
    assert rows.identity.model=='DS-test'
    assert 'autenticado' in rows.notice.lower()

def test_protocol_override_routes_compatible_oem_without_changing_brand():
    from artin_sentinel.hik_recording import uses_hikvision_recordings
    assert uses_hikvision_recordings({'manufacturer':'Outra marca','provider':'generic','metadata_json':'{"recorder_protocol":"hikvision"}'})
    assert uses_hikvision_recordings({'manufacturer':'HiLook','provider':'hikvision'})
    assert not uses_hikvision_recordings({'manufacturer':'Intelbras','provider':'intelbras'})

def test_device_info_html_is_not_authenticated_inventory(monkeypatch):
    from artin_sentinel import native_protocols as native
    monkeypatch.setattr(native,'build_opener',lambda *args:Opener([b'<html><body>Login</body></html>']))
    result=native.probe_hikvision_isapi_device_info('192.0.2.1','u','p')
    assert not result.authenticated

def test_ui_finishes_authenticated_empty_scan_preserving_saved_channels():
    from artin_sentinel.app import MainWindow
    device={'id':1,'site_id':1,'name':'DVR','ip':'192.0.2.1','kind':'dvr','manufacturer':'Hikvision','provider':'hikvision'}
    saved=[{'channel_no':1,'available':True}];shown=[];writes=[]
    db=NS(list_recorder_channels=lambda _:saved,replace_recorder_channels=lambda *a,**k:writes.append(a),
          apply_detected_identity=lambda *a,**k:None,add_event=lambda *a:None,get_device=lambda _:device)
    host=NS(db=db,access_control=None,channel_scan_context={'device_id':1,'device':device,'wait':NS(close=lambda:None)},
            refresh_all=lambda:None,channels_button=NS(setEnabled=lambda _:None),
            _resume_monitor_after_recorder=lambda:None,show_channel_rows=lambda dev,rows,**kw:shown.append((rows,kw)))
    rows=recorder.RecorderScanResult((),preserve_existing=True,notice='DVR autenticado; sem canais anunciados.')
    MainWindow._finish_recorder_channel_scan(host,rows)
    assert not writes
    assert shown[0][0] is saved and 'autenticado' in shown[0][1]['notice']
    assert host.channel_scan_context is None

def test_returned_segment_routes_seek_and_export_to_enrolled_host():
    from artin_sentinel.hik_recording import hikvision_playback_url
    from artin_sentinel.recording_search import Recording
    from urllib.parse import urlparse,parse_qs
    row=Recording(1,'2026-10-21 09:00:00','2026-10-21 10:00:00','normal',0,
        'rtsp://192.0.2.44/Streaming/tracks/101/?starttime=20261021T120000Z&endtime=20261021T130000Z')
    uri=hikvision_playback_url(row,'http://[2001:db8::1]',datetime(2026,10,21,9,15),datetime(2026,10,21,9,20),port=10554)
    parsed=urlparse(uri)
    assert parsed.hostname=='2001:db8::1' and parsed.port==10554
    assert parse_qs(parsed.query)['starttime']==['20261021T121500Z']
    with pytest.raises(RecordingSearchError):
        hikvision_playback_url(row,'http://192.0.2.1',datetime(2026,10,21,8),datetime(2026,10,21,9,20))

def test_calendar_for_explicit_protocol_uses_hikvision_search(monkeypatch):
    from datetime import date
    import artin_sentinel.hik_recording as hik
    from artin_sentinel.recording_history import run_history
    from artin_sentinel.recording_search import SearchResult
    calls=[]
    monkeypatch.setattr(hik,'search_hikvision_recordings',lambda *args:(calls.append(args) or SearchResult(())))
    dev={'manufacturer':'Outra Marca','provider':'generic','metadata_json':'{"recorder_protocol":"hikvision"}','web_url':'http://192.0.2.1'}
    result=run_history(dev,'http://192.0.2.1','u','p',1,[date(2026,10,21)])
    assert len(calls)==1 and result.days[0].state=='empty'


import pytest as _pytest
from types import SimpleNamespace as _NS
@_pytest.fixture(autouse=True)
def _configured_ip_inventory_stub(monkeypatch):
    import artin_sentinel.recorder as _recorder
    monkeypatch.setattr(_recorder, 'probe_hikvision_input_proxy_channels',
                        lambda *a, **k: _NS(channels=(), detail='sem entradas configuradas'))

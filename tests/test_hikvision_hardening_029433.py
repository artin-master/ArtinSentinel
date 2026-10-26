from datetime import datetime
import pytest

from artin_sentinel.hik_recording import search_hikvision_recordings, hikvision_playback_url
from artin_sentinel.recording_search import Recording, RecordingSearchError


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return self.data


class Opener:
    def __init__(self,data): self.data=data; self.requests=[]
    def open(self,request,timeout): self.requests.append(request); return Response(self.data)


def test_search_declares_video_metadata_and_preserves_size(monkeypatch):
    xml=b'''<CMSearchResult><responseStatus>true</responseStatus><responseStatusStrg>OK</responseStatusStrg>
    <searchMatchItem><trackID>101</trackID><timeSpan><startTime>2026-10-26T12:00:00Z</startTime>
    <endTime>2026-10-26T12:05:00Z</endTime></timeSpan><mediaSegmentDescriptor>
    <playbackURI>rtsp://192.0.2.5/Streaming/tracks/101/?starttime=20261026T120000Z&amp;endtime=20261026T120500Z&amp;size=98765</playbackURI>
    </mediaSegmentDescriptor></searchMatchItem></CMSearchResult>'''
    opener=Opener(xml)
    monkeypatch.setattr("artin_sentinel.hik_recording._local_time",lambda value:datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ"))
    result=search_hikvision_recordings("http://192.0.2.1","admin","private",1,
        datetime(2026,10,26,12),datetime(2026,10,26,13),opener=opener)
    body=opener.requests[0].data
    assert b"<contentType>video</contentType>" in body
    assert b"//recordType.meta.std-cgi.com" in body
    assert result.recordings[0].size==98765


def test_response_status_reports_sanitized_substatus():
    opener=Opener(b"<ResponseStatus><statusString>Invalid XML</statusString><subStatusCode>badXmlContent</subStatusCode></ResponseStatus>")
    with pytest.raises(RecordingSearchError,match="badXmlContent"):
        search_hikvision_recordings("http://192.0.2.1","admin","private",1,
            datetime(2026,10,26,12),datetime(2026,10,26,13),opener=opener)


def test_playback_rejects_embedded_credentials_and_invalid_track_path():
    base=dict(channel=1,start="2026-10-26 12:00:00",end="2026-10-26 12:05:00",kind="normal",size=0)
    for uri in (
        "rtsp://user:secret@192.0.2.5/Streaming/tracks/101/?starttime=20261026T120000Z&endtime=20261026T120500Z",
        "rtsp://192.0.2.5/Streaming/tracks/101/extra?starttime=20261026T120000Z&endtime=20261026T120500Z",
    ):
        row=Recording(**base,playback_uri=uri)
        with pytest.raises(RecordingSearchError):
            hikvision_playback_url(row,"http://192.0.2.1",datetime(2026,10,26,12),datetime(2026,10,26,12,1))

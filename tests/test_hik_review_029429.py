from datetime import datetime
from threading import Event
import pytest
from test_hik_playback_029428 import Opener,page
from artin_sentinel.hik_recording import search_hikvision_recordings,search_hikvision_recordings_multi
from artin_sentinel.recording_search import RecordingSearchError

def test_cancelled_search_never_submits_a_request():
    cancel=Event();cancel.set();op=Opener([])
    with pytest.raises(RecordingSearchError,match='cancelada'):
        search_hikvision_recordings('http://192.0.2.1','u','p',1,datetime(2026,10,21),datetime(2026,10,22),opener=op,cancel_event=cancel)
    assert not op.requests

def test_repeated_more_page_stops_with_partial_result():
    op=Opener([page('MORE')]*8)
    r=search_hikvision_recordings('http://192.0.2.1','u','p',1,datetime(2026,10,21),datetime(2026,10,22),opener=op)
    assert len(op.requests)==2 and r.truncated and r.warnings

def test_multichannel_search_preserves_ignored_evidence(monkeypatch):
    import artin_sentinel.hik_recording as h
    from artin_sentinel.recording_search import SearchResult
    monkeypatch.setattr(h,'search_hikvision_recordings',lambda *a,**k:SearchResult((),ignored=1))
    r=search_hikvision_recordings_multi('http://192.0.2.1','u','p',[1,2],datetime(2026,10,21),datetime(2026,10,22))
    assert r.ignored==2

def test_matches_status_is_a_valid_search_response():
    op=Opener([page('MATCHES')])
    r=search_hikvision_recordings('http://192.0.2.1','u','p',1,datetime(2026,10,21),datetime(2026,10,22),opener=op)
    assert len(r.recordings)==1

def test_hikvision_route_reaches_shared_video_and_audio_commands():
    from artin_sentinel.app import MainWindow
    from artin_sentinel.recording_search import Recording
    from artin_sentinel.live import LiveStreamSession,LiveAudioSession
    from types import SimpleNamespace
    row=Recording(1,'2026-10-21 09:00:00','2026-10-21 10:00:00','normal',0,
        'rtsp://192.0.2.9/Streaming/tracks/101/?starttime=20261021T120000Z&endtime=20261021T130000Z')
    uri=MainWindow.recording_route(SimpleNamespace(),row,'http://192.0.2.1',1,datetime(2026,10,21,9,5),datetime(2026,10,21,9,6),554)
    video=LiveStreamSession(uri,playback=True,playback_speed=8)
    command=video._command(uri)
    assert command[command.index('-readrate')+1]=='8'
    assert 'setpts=PTS/8' in command[command.index('-vf')+1]
    audio=LiveAudioSession(uri,playback=True,playback_speed=1)
    assert audio.url==uri and video.url==uri

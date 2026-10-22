"""No network: C++ NetSDK fixture, local callbacks and descriptor IPC only."""
from datetime import datetime,timedelta
from pathlib import Path
import subprocess,threading
import pytest
from test_persistent_playback_029422 import persistent_sdk,acquire_pipe,wait_stage

@pytest.fixture
def query_sdk(persistent_sdk,monkeypatch):
    from artin_sentinel.playback_session_pool import PlaybackSessionPool
    import artin_sentinel.playback_session_pool as module
    p=persistent_sdk/'fake.cpp';source=p.read_text()
    source=source.replace('if(login!=0x123456789L || channel!=0 || type || card', 'trace("query");if(scenario("query_failed"))return 0; if(login!=0x123456789L || (channel<0 || channel>3) || type || card')
    source=source.replace('out[0].channel=0;out[0].size=1;', 'out[0].channel=channel;out[0].size=1;')
    p.write_text(source)
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-pthread',str(p),'-o',str(persistent_sdk/'libdhnetsdk.so')],check=True)
    pool=PlaybackSessionPool();monkeypatch.setattr(module,'_pool',pool)
    yield persistent_sdk,pool
    pool.shutdown()

ROUTE='intelbras-cloud://127.0.0.1:55162/1?serial=TEST-SERIAL-PRIVATE'
START=datetime(2026,10,19,8)

def search(sdk,channels=(1,),start=START,**kwargs):
    from artin_sentinel.intelbras_cloud_recordings import search_cloud_recordings
    return search_cloud_recordings(ROUTE,'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',channels,start,start+timedelta(hours=1),sdk_dir=sdk,**kwargs)

def test_repeated_day_search_and_multiple_channels_share_one_login(query_sdk):
    sdk,pool=query_sdk
    first=search(sdk);assert len(first.recordings)==1
    assert 'novas: 1' in first.diagnostics[0]
    second=search(sdk,start=START-timedelta(days=1));assert not second.recordings
    assert 'novas: 0' in second.diagnostics[0] and 'reutilizada: 1' in second.diagnostics[0]
    assert [r.channel for r in search(sdk,channels=(1,2)).recordings]==[1,2]
    trace=(sdk/'trace').read_text().splitlines()
    assert trace.count('login')==1 and trace.count('query')==4
    assert trace.count('logout')==0
    pool.shutdown()
    assert (sdk/'trace').read_text().splitlines().count('logout')==1

def test_queries_do_not_stop_active_playback(query_sdk):
    sdk,pool=query_sdk;client=None;thread=None
    try:
        client,_,thread=acquire_pipe(pool,sdk)
        wait_stage(client,'stream_data_received');pid=client.process.pid
        assert len(search(sdk).recordings)==1
        assert client.process.pid==pid and client.process.poll() is None
        assert client.client.cancel_fd>=0
        assert (sdk/'trace').read_text().splitlines().count('login')==2
    finally:
        if client:client.close()
        if thread:thread.join(3)

def test_failed_query_is_not_retried_or_cached(query_sdk,monkeypatch):
    from artin_sentinel.recording_search import RecordingSearchError
    sdk,pool=query_sdk;monkeypatch.setenv('FAKE_SCENARIO','query_failed')
    with pytest.raises(RecordingSearchError):search(sdk)
    assert not pool.entries
    trace=(sdk/'trace').read_text().splitlines()
    assert trace.count('login')==1 and trace.count('query')==1

def test_canceled_search_does_not_create_login(query_sdk):
    from artin_sentinel.recording_search import RecordingSearchError
    sdk,pool=query_sdk;cancel=threading.Event();cancel.set()
    with pytest.raises(RecordingSearchError,match='cancelada'):search(sdk,cancel_event=cancel)
    assert not pool.entries and not (sdk/'trace').exists()

def test_serial_mismatch_does_not_reuse_or_replace_the_valid_session(query_sdk):
    from artin_sentinel.intelbras_cloud_recordings import search_cloud_recordings
    from artin_sentinel.recording_search import RecordingSearchError
    sdk,pool=query_sdk
    assert len(search(sdk).recordings)==1
    with pytest.raises(RecordingSearchError,match='serial'):
        search_cloud_recordings(ROUTE.replace('TEST-SERIAL-PRIVATE','WRONG-SERIAL'),'TEST-USER-PRIVATE','TEST-PASSWORD-PRIVATE',(1,),START,START+timedelta(hours=1),sdk_dir=sdk)
    assert len(search(sdk).recordings)==1
    trace=(sdk/'trace').read_text().splitlines()
    assert trace.count('login')==2 and trace.count('query')==2

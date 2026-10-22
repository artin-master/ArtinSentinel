from types import SimpleNamespace as NS

def test_speed_selection_uses_fresh_media_instead_of_native_seek():
    from artin_sentinel.app import MainWindow
    calls=[]
    host=NS(playback_session=object(),playback_clip_bounds=(1,2),seek_playback_stream=lambda **kw:calls.append(kw))
    MainWindow.change_playback_speed(host)
    assert calls==[{'force_reopen':True}]

def test_change_during_playback_reopens_at_cursor_with_requested_rate(monkeypatch):
    from datetime import datetime
    from artin_sentinel.app import MainWindow
    import artin_sentinel.app as module
    from artin_sentinel import playback_layout
    calls=[];start=datetime(2026,10,19,8);end=datetime(2026,10,19,9)
    old=NS(request_playback_seek=lambda *a:(_ for _ in ()).throw(AssertionError('native seek used for speed')))
    replacement=NS(start=lambda:calls.append('started'))
    def create(url,*args,**kwargs):
        assert kwargs['playback_speed']==8 and kwargs['playback'] is True
        assert url=='route-at-120';calls.append('created');return replacement
    monkeypatch.setattr(module,'create_live_stream_session',create)
    monkeypatch.setattr(playback_layout,'set_video_busy',lambda *a:None)
    host=NS(db=NS(get_device=lambda _:None),playback_device_combo=NS(currentData=lambda:None),playback_clip_bounds=(start,end),playback_seek=NS(value=lambda:120,setEnabled=lambda x:None),
        playback_multi_check=NS(isChecked=lambda:False),selected_playback_clip=lambda:('127.0.0.1',37777,1,start,end,('u','p')),
        selected_recording_row=lambda:None,recording_route=lambda *a:'route-at-120',playback_session=old,
        playback_listen_check=NS(isChecked=lambda:False),playback_speed_combo=NS(currentData=lambda:8),
        stop_playback_stream=lambda **kw:calls.append('old-stopped'),playback_screen=NS(setText=lambda x:None),
        playback_stop_btn=NS(setEnabled=lambda x:None),toggle_playback_audio=lambda:None)
    host.seek_playback_stream=lambda **kw:MainWindow.seek_playback_stream(host,**kw)
    MainWindow.change_playback_speed(host)
    assert calls==['old-stopped','created','started']
    assert host.playback_session is replacement and host.playback_offset_seconds==120


def test_playback_selector_stops_at_eight():
    from PySide6.QtWidgets import QApplication,QMainWindow,QStackedWidget
    from artin_sentinel.app import MainWindow
    import shiboken6
    app=QApplication.instance() or QApplication([])
    window=MainWindow.__new__(MainWindow);QMainWindow.__init__(window)
    window.pages=QStackedWidget();window.setCentralWidget(window.pages)
    window.playback_session=None;window.playback_audio_session=None;window.playback_sessions={};window.playback_active_channels=[]
    MainWindow.build_playback_page(window)
    assert [window.playback_speed_combo.itemData(i) for i in range(window.playback_speed_combo.count())]==[.5,1.,2.,4.,8.]
    window.playback_poll_timer.stop();window.playback_day_search_timer.stop();shiboken6.delete(window)

def test_header_has_clear_wordmark_without_operational_tagline():
    from PySide6.QtWidgets import QApplication,QMainWindow,QLabel
    from artin_sentinel.app import MainWindow
    import shiboken6
    app=QApplication.instance() or QApplication([])
    window=MainWindow.__new__(MainWindow);QMainWindow.__init__(window)
    bar=MainWindow.build_topbar(window)
    texts=[label.text() for label in bar.findChildren(QLabel)]
    assert 'ARTIN' in texts and 'SENTINEL' in texts
    assert 'Monitoramento CFTV multimarcas' not in texts
    assert bar.height()==68
    bar.deleteLater();shiboken6.delete(window);app.processEvents()

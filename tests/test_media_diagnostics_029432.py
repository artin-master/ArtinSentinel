from artin_sentinel.runtime_diagnostics import RuntimeLog

def test_repetitive_ffmpeg_rate_warnings_do_not_erase_export_error():
    log=RuntimeLog(limit=50)
    log.append('exportação','Falha ao finalizar MP4')
    for i in range(1000):log.append('reprodução',f'Resumed reading at pts {i} with rate 8.400 after a lag of {i}s')
    assert 'Falha ao finalizar MP4' in log.text()
    assert len(log.lines)<15

def test_ffmpeg_observation_preserves_source_resolution():
    from artin_sentinel.media_observation import observe_video
    got=observe_video('Stream #0:0: Video: h264 (High), yuv420p, 1280x720 [SAR 1:1 DAR 16:9], 15 fps')
    assert got=={'codec':'H.264','width':1280,'height':720,'fps':15.0}
    assert observe_video('nenhuma evidência') is None

def test_access_policy_uses_brand_without_inventing_channel_mapping():
    from artin_sentinel.access_policy import recommendation
    got=recommendation('Hikvision','dvr',True)
    assert got['provider']=='hikvision' and got['sdk']=='hikvision'
    assert 'channels' not in got
    assert recommendation('Intelbras','camera',True)['sdk']==''

def test_component_registry_is_extensible():
    from artin_sentinel.components import ComponentRegistry
    reg=ComponentRegistry();reg.register('test','Novo SDK',lambda:{'state':'Disponível','detail':'sem login'})
    assert reg.inspect()[0]['name']=='Novo SDK'
    assert reg.inspect()[0]['state']=='Disponível'

def test_export_reports_sanitized_native_error(tmp_path,monkeypatch):
    import artin_sentinel.recording_export as module
    fake=tmp_path/'ffmpeg'
    fake.write_text('#!/usr/bin/env python3\nimport sys\nprint("Falha muxer rtsp://admin:secret@192.0.2.1/arquivo",file=sys.stderr)\nsys.exit(1)\n')
    fake.chmod(0o755)
    monkeypatch.setattr(module.shutil,'which',lambda _:str(fake))
    import pytest
    with pytest.raises(module.RecordingExportError) as err:
        module.export_mp4('rtsp://192.0.2.1/live','admin','secret',str(tmp_path/'out.mp4'),10)
    assert 'muxer' in str(err.value) and 'secret' not in str(err.value)
    assert not (tmp_path/'out.mp4').exists()

def test_hikvision_speed_commands_are_sent_to_recorder():
    from artin_sentinel.hik_sdk_worker import apply_speed
    calls=[]
    assert apply_speed(lambda *args:calls.append(args[1]) or True,7,8)
    assert calls==[7,5,5,5]
    calls.clear()
    assert not apply_speed(lambda *args:calls.append(args[1]) or False,7,4)
    assert calls==[7]

def test_export_rejects_truncated_clip_and_native_failure(tmp_path):
    import subprocess
    from artin_sentinel.recording_export import validate_export_media,RecordingExportError
    import pytest
    sample=tmp_path/'short.mp4'
    subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','testsrc=size=128x72:rate=10','-t','2','-c:v','mpeg4',str(sample)],check=True,timeout=10)
    with pytest.raises(RecordingExportError,match='incompleto'):validate_export_media(sample,20,[])
    with pytest.raises(RecordingExportError,match='SDK'):validate_export_media(sample,2,[{'stage':'error','operation':'no_media_timeout'}])
    validate_export_media(sample,2,[])

def test_audio_duration_cannot_hide_truncated_video(tmp_path):
    import subprocess,pytest
    from artin_sentinel.recording_export import validate_export_media,RecordingExportError
    sample=tmp_path/'long-audio.mp4'
    subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','testsrc=size=128x72:rate=10:duration=2',
        '-f','lavfi','-i','sine=frequency=1000:duration=8','-c:v','mpeg4','-c:a','aac',str(sample)],check=True,timeout=10)
    with pytest.raises(RecordingExportError,match='incompleto'):validate_export_media(sample,8,[])

def test_later_native_error_is_not_hidden_by_expected_pipe_close(tmp_path):
    import subprocess,pytest
    from artin_sentinel.recording_export import validate_export_media,RecordingExportError
    sample=tmp_path/'video.mp4'
    subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','testsrc=size=128x72:rate=10:duration=2','-c:v','mpeg4',str(sample)],check=True,timeout=10)
    with pytest.raises(RecordingExportError,match='SDK'):
        validate_export_media(sample,2,[{'stage':'error','operation':'media_queue_or_pipe'},{'stage':'error','operation':'playback_tail_incomplete'}])

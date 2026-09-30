from pathlib import Path


def test_live_view_uses_ffmpeg_worker_and_main_thread_polling():
    app = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    live = Path("artin_sentinel/live.py").read_text(encoding="utf-8")
    assert "LiveStreamSession" in app
    assert "poll_live_streams" in app
    assert "QTimer" in app
    assert "subprocess.Popen" in live
    assert "rawvideo" in live
    assert "QImage" in app


def test_recorder_dialog_offers_secure_save_and_friendly_name():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    start = source.index("    def read_recorder_channels(self):")
    end = source.index("    def _start_recorder_channel_scan", start)
    flow = source[start:end]
    assert "Nome amigável" in flow
    assert "Salvar credencial com segurança" in flow
    assert "credential_store.set_password" in flow
    assert ".exec()" not in flow


def test_channel_ui_has_stream_modes_and_alias_action():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'self.stream_combo.addItem("Automático", "auto")' in source
    assert 'self.stream_combo.addItem("Substream", "sub")' in source
    assert 'self.stream_combo.addItem("Main stream", "main")' in source
    assert "Renomear câmera / canal" in source

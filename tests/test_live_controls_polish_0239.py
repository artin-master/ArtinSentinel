from pathlib import Path


def _app_source() -> str:
    return Path("artin_sentinel/app.py").read_text(encoding="utf-8")


def test_tile_mic_pending_is_deliberately_visible_and_labeled():
    source = _app_source()
    assert 'self._audio_talk_pending = False' in source
    assert 'self.talk_button.setText("MIC OFF")' in source
    assert 'self.talk_button.setEnabled(False)' in source
    assert 'MIC indisponível neste canal' in source
    assert 'talk_pending=bool(audio_info.get("talkback_pending"))' in source


def test_inspector_mic_pending_is_explicit_not_just_greyed():
    source = _app_source()
    assert 'self.talkback_btn.setText("MIC INDISP.")' in source
    assert 'self.talkback_btn.setVisible(can_talk or talkback_pending)' in source
    assert 'NetSDK Intelbras não pronto' in source


def test_tile_context_menu_is_grouped_and_stateful():
    source = _app_source()
    assert 'menu.addSection("VISUALIZAÇÃO")' in source
    assert 'menu.addSection("ÁUDIO")' in source
    assert 'menu.addSection("CANAL")' in source
    assert 'act.setCheckable(True)' in source
    assert 'Push-to-Talk  —  INDISPONÍVEL' in source
    assert 'Diagnóstico do Live View / áudio' in source
    assert 'Pausar reconexão automática' in source
    assert 'Retomar conexão' in source


def test_context_menu_uses_operational_audio_context():
    source = _app_source()
    start = source.index('    def show_tile_context_menu(self, tile: VideoTile, pos):')
    end = source.index('    def _restore_mosaic_after_focused_close', start)
    block = source[start:end]
    assert 'ctx = self._audio_context_for_tile(tile)' in block
    assert 'talkback_netsdk_runtime' in block
    assert 'NetSDK Intelbras necessário' in block

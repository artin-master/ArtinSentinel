from pathlib import Path

import artin_sentinel.ptz as ptz
from artin_sentinel import __version__


def test_release_version_0216(release_version):
    assert __version__ == release_version


def test_compact_toolbar_and_contextual_inspector_are_present():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "ToolbarIconAction" in source
    assert '"Limpar mosaico"' in source
    assert '"Nova janela de monitoramento"' in source
    assert '"Tela cheia do mosaico"' in source
    assert "self.stream_section.hide()" in source
    assert "self.audio_section.hide()" in source
    assert "self.ptz_section.hide()" in source
    assert "Push-to-Talk" in source


def test_ptz_press_release_wiring_is_present():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "btn.pressed.connect" in source
    assert "btn.released.connect(self.stop_selected_ptz_hold)" in source
    assert "start_selected_ptz_hold" in source
    assert "renew_selected_ptz_hold" in source
    assert "_ptz_command_pending" in source


def test_start_move_is_bounded_and_does_not_sleep(monkeypatch):
    calls = {}
    context = ptz.OnvifPtzContext(
        device_url="http://cam/onvif/device_service",
        media_url="http://cam/onvif/media_service",
        ptz_url="http://cam/onvif/ptz_service",
        profile_token="profile0",
    )

    monkeypatch.setattr(ptz, "discover_onvif_ptz_context", lambda *args, **kwargs: context)

    def fake_continuous(ctx, username, password, direction, speed, *, timeout_seconds):
        calls.update(
            ctx=ctx,
            username=username,
            password=password,
            direction=direction,
            speed=speed,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr(ptz, "continuous_move", fake_continuous)
    result = ptz.start_move("192.0.2.10", "admin", "secret", "", "left", speed=0.7, safety_timeout=1.2)

    assert calls["ctx"] == context
    assert calls["direction"] == "left"
    assert calls["speed"] == 0.7
    assert 0.35 <= calls["timeout_seconds"] <= 1.5
    assert "contínuo" in result


def test_inspector_uses_vertical_scroll_instead_of_compressing_controls():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "QScrollArea" in source
    assert 'setObjectName("InspectorScroll")' in source
    assert "setWidgetResizable(True)" in source
    assert "setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)" in source
    assert "setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)" in source
    assert "ins.setSizeConstraint(QLayout.SetMinimumSize)" in source
    assert "btn.setFixedSize(52, 46)" in source


def test_site_status_moved_to_bottom_bar_and_config_button_removed():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'self.live_health = QLabel("Site: — · 0 equipamentos · 0 online")' in source
    assert 'self.live_health_icon = self._standard_icon_label("SP_ComputerIcon"' in source
    assert 'layout.addWidget(self.live_health)' in source
    assert 'self.bottom_notice = QLabel("")' in source
    assert '"Abrir configuração"' not in source


def test_rare_live_actions_are_in_compact_overflow_menu():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'self.inspector_menu_btn.setText("⋮")' in source
    assert 'self.rename_channel_action = self.inspector_menu.addAction("Renomear câmera / canal")' in source
    assert 'self.ask_stream_action = self.inspector_menu.addAction("Perguntar qual stream ao abrir")' in source
    assert 'self.ask_stream_check.hide()' in source


def test_inspector_selection_uses_icon_card_instead_of_prose_block():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert 'self.selection_card.setObjectName("SelectionCard")' in source
    assert 'self.live_selection_icon = QLabel()' in source
    assert 'self.live_selection_title.setObjectName("SelectionTitle")' in source
    assert 'self.live_selection_meta.setObjectName("SelectionMeta")' in source
    assert 'self.live_selection_status.setObjectName("SelectionState")' in source
    assert '_refresh_live_selection_from_tile' in source


def test_stream_audio_ptz_and_diagnostics_use_compact_icons():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert '_standard_icon_label("SP_MediaPlay", "Stream de vídeo"' in source
    assert '_standard_icon_label("SP_MediaVolume", "Áudio ao vivo"' in source
    assert '_standard_icon_label("SP_ArrowUp", "Controle PTZ / Speed Dome"' in source
    assert 'SP_MessageBoxInformation' in source
    assert 'titanium_icon("stop" if active else "audio", 20)' in source

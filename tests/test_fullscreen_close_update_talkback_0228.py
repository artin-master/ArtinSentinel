from pathlib import Path

from artin_sentinel import __version__
from artin_sentinel.akdb import audio_capability
from artin_sentinel.updater import DEFAULT_MANIFEST_BASE_URL, resolve_manifest_url
from artin_akdb import CORE_REVISION, record_by_legacy_key


def test_release_0228_and_official_artinupdates_default(release_version):
    assert __version__ == release_version
    assert DEFAULT_MANIFEST_BASE_URL == "https://raw.githubusercontent.com/artin-master/ArtinUpdates/main"
    assert resolve_manifest_url(DEFAULT_MANIFEST_BASE_URL, "stable") == (
        "https://raw.githubusercontent.com/artin-master/ArtinUpdates/main/sentinel/stable.json"
    )
    assert resolve_manifest_url(DEFAULT_MANIFEST_BASE_URL, "beta") == (
        "https://raw.githubusercontent.com/artin-master/ArtinUpdates/main/sentinel/beta.json"
    )


def test_main_focused_close_restores_mosaic_before_workspace_save():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    block = source[source.index("    def close_tile_source(self, tile: VideoTile):"):source.index("    def pause_tile_reconnect", source.index("    def close_tile_source(self, tile: VideoTile):"))]
    assert "focused = bool(self._focus_return_state is not None" in block
    assert "self._restore_mosaic_after_focused_close(tile)" in block
    assert block.index("self._restore_mosaic_after_focused_close(tile)") < block.index("self.save_live_workspace()")

    helper = source[source.index("    def _restore_mosaic_after_focused_close"):source.index("    def close_tile_source", source.index("    def _restore_mosaic_after_focused_close"))]
    assert "self._focus_return_state = None" in helper
    assert "self._restore_video_grid_geometry()" in helper
    assert "stop_tile_stream" not in helper
    assert "t.source" in helper


def test_workspace_save_uses_live_tiles_even_during_focus():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    block = source[source.index("    def save_live_workspace(self, *_args):"):source.index("    def restore_live_workspace", source.index("    def save_live_workspace(self, *_args):"))]
    assert '_focus_return_state.get("slots"' not in block
    assert "for tile in self.video_tiles:" in block


def test_detached_monitor_close_exits_individual_fullscreen():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    start = source.index("class DetachedMonitorWindow")
    end = source.index("class MainWindow", start)
    detached = source[start:end]
    close = detached[detached.index("    def close_tile(self,tile):"):detached.index("    def source_clicked", detached.index("    def close_tile(self,tile):"))]
    assert "focused = self._individual_fullscreen_tile is tile" in close
    assert "self._exit_camera_fullscreen(select_fallback=True" in close
    helper = detached[detached.index("    def _exit_camera_fullscreen"):detached.index("    def toggle_camera_fullscreen", detached.index("    def _exit_camera_fullscreen"))]
    assert "for t in self.video_tiles:" in helper
    assert "t.show()" in helper
    assert "self.select_tile(candidates[0])" in helper


def test_itblue_talkback_is_experimental_not_homologated():
    assert CORE_REVISION >= 8
    audio = audio_capability(profile_key="it-blue-x3-we2q")
    assert audio["mode"] == "bidirectional"
    assert audio["talkback_protocol"] == "xm-dvrip-g711a-experimental"
    core = record_by_legacy_key("it-blue-x3-we2q")
    assert core is not None
    assert "xm-dvrip-talkback-g711a-experimental" in core.protocols
    assert "xm-dvrip-talkback-not-field-validated" in core.negative_knowledge

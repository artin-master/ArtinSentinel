from pathlib import Path

from artin_sentinel.workspace import SUPPORTED_GRID_COUNTS, smallest_grid_for, next_empty_slot


def test_large_mosaic_options_include_100_plus():
    assert 100 in SUPPORTED_GRID_COUNTS
    assert 144 in SUPPORTED_GRID_COUNTS


def test_smallest_grid_for_hybrid_recorder():
    assert smallest_grid_for(5) == 9
    assert smallest_grid_for(18) == 25
    assert smallest_grid_for(101) == 144


def test_next_empty_slot_wraps_without_overwriting():
    sources = [object(), None, object(), None]
    assert next_empty_slot(sources, 0) == 1
    assert next_empty_slot(sources, 1) == 3
    assert next_empty_slot([object(), object()], 0) is None


def test_app_has_single_click_and_open_all_flow():
    text = Path('artin_sentinel/app.py').read_text(encoding='utf-8')
    assert 'itemClicked.connect(self.source_single_clicked)' in text
    assert 'def open_all_device_channels' in text
    assert 'self._select_next_empty_tile(tile.index)' in text


def test_device_management_is_visible_and_contextual():
    text = Path('artin_sentinel/app.py').read_text(encoding='utf-8')
    assert 'Excluir permanentemente' in text
    assert 'Arquivar / remover do Site' in text
    assert 'show_device_context_menu' in text

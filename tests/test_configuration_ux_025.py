from pathlib import Path


def test_configuration_uses_compact_primary_actions():
    text = Path('artin_sentinel/app.py').read_text(encoding='utf-8')
    for label in ('"Adicionar"', '"Editar"', '"Diagnosticar"', '"Canais"', '"Mais ▾"'):
        assert label in text
    assert 'self.dev_table = QTableWidget(0, 9)' in text
    assert '["Nome", "IP", "Tipo", "Fabricante / modelo", "Estado", "Canais", "Áudio", "Confiança", "Credencial"]' in text


def test_site_management_is_exposed_and_safe():
    text = Path('artin_sentinel/app.py').read_text(encoding='utf-8')
    assert 'def rename_selected_site' in text
    assert 'def archive_selected_site' in text
    assert 'def show_archived_sites' in text
    assert 'def delete_selected_site' in text
    assert 'Mover equipamentos para outro Site' in text
    assert 'Excluir Site e todos os equipamentos' in text

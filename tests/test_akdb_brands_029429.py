from dataclasses import replace
import sqlite3
import pytest

def test_brand_defaults_aliases_and_persistence_without_core_promotion(tmp_path):
    from artin_akdb.brands import BrandRegistry
    path=tmp_path/'akdb.sqlite3';registry=BrandRegistry(path)
    intel=registry.resolve('INTELBRAS');assert intel.name=='Intelbras'
    assert intel.color=='#55D996'
    registry.save(replace(intel,color='#80DEEA',aliases=('Intelbras Brasil',)))
    fresh=BrandRegistry(path)
    assert fresh.resolve('intelbras brasil').id==intel.id
    assert fresh.resolve('Intelbras').color=='#80DEEA'
    with sqlite3.connect(path) as c:
        assert c.execute('select count(*) from records').fetchone()[0]==0
        assert c.execute('select count(*) from manufacturer_preference_history').fetchone()[0]==1

def test_invalid_color_or_ambiguous_alias_does_not_change_database(tmp_path):
    from artin_akdb.brands import BrandRegistry
    r=BrandRegistry(tmp_path/'akdb.sqlite3');intel=r.resolve('Intelbras')
    with pytest.raises(ValueError):r.save(replace(intel,aliases=('Hikvision',)))
    with pytest.raises(ValueError):r.save(replace(intel,color='red;bad'))
    assert r.resolve('Intelbras')==intel

def test_unknown_manufacturer_has_neutral_color_not_provider_guess(tmp_path):
    from artin_akdb.brands import BrandRegistry
    from artin_sentinel.brand_tree import brand_presentation
    r=BrandRegistry(tmp_path/'akdb.sqlite3')
    label,span=brand_presentation({'name':'DVR antigo','manufacturer':'Outra Marca','provider':'hikvision'},r)
    assert label=='DVR antigo · Outra Marca' and span[2]=='#AABBC8'
    label,span=brand_presentation({'name':'Meu Intelbras','manufacturer':'Intelbras'},r)
    assert label=='Meu Intelbras' and span is None
    label,span=brand_presentation({'name':'Sala','manufacturer':'intelbras'},r)
    assert label=='Sala · Intelbras' and label[span[0]:span[0]+span[1]]=='Intelbras'

def test_brand_name_is_not_added_to_channels(tmp_path):
    from PySide6.QtWidgets import QApplication,QTreeWidget,QTreeWidgetItem
    from artin_akdb.brands import BrandRegistry
    from artin_sentinel.brand_tree import decorate_device_item,BRAND_ROLE
    app=QApplication.instance() or QApplication([])
    tree=QTreeWidget();parent=QTreeWidgetItem(tree,['Sala']);child=QTreeWidgetItem(parent,['Canal 01'])
    decorate_device_item(parent,{'name':'Sala','manufacturer':'Hikvision'},BrandRegistry(tmp_path/'a.db'))
    assert parent.data(0,BRAND_ROLE) is not None
    assert child.text(0)=='Canal 01' and child.data(0,BRAND_ROLE) is None
    tree.close()

def test_color_update_survives_official_sync_and_does_not_change_schema(tmp_path):
    from artin_akdb.brands import BrandRegistry
    from artin_akdb import SharedAkdbStore,SCHEMA_VERSION
    p=tmp_path/'akdb.db';r=BrandRegistry(p)
    r.save(replace(r.resolve('Hikvision'),color='#FFAB66'))
    with SharedAkdbStore(p) as s:
        s.sync_catalog()
        assert int(s._meta('schema_version'))==SCHEMA_VERSION
    assert BrandRegistry(p).resolve('Hikvision').color=='#FFAB66'

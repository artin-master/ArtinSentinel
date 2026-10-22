from pathlib import Path
import importlib.util


def load_check():
    spec=importlib.util.spec_from_file_location('cloud_ready',Path(__file__).parents[1]/'tools/check_cloud_ready.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_ready_cloud_skips_reconfiguration(tmp_path):
    check=load_check()
    prefix=tmp_path/'wine';compiler=prefix/'drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    compiler.parent.mkdir(parents=True);compiler.write_bytes(b'compiler')
    from types import SimpleNamespace
    manager=SimpleNamespace(prefix=prefix,installed=lambda:True)
    assert check.cloud_ready(manager=manager,which=lambda _: '/usr/bin/wine')
    compiler.unlink();assert not check.cloud_ready(manager=manager,which=lambda _: '/usr/bin/wine')


def test_missing_wine_or_changed_bridge_requires_setup(tmp_path):
    check=load_check()
    from types import SimpleNamespace
    manager=SimpleNamespace(prefix=tmp_path,installed=lambda:False)
    assert not check.cloud_ready(manager=manager,which=lambda _:None)
    assert not check.cloud_ready(manager=manager,which=lambda _: '/usr/bin/wine')


def test_reuse_check_happens_before_question():
    script=(Path(__file__).parents[1]/'install.sh').read_text()
    check=script.index('tools/check_cloud_ready.py')
    assert check<script.index('Preparar também Intelbras Cloud')
    assert 'Cloud já preparado; ambiente existente preservado.' in script

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
import pytest

spec=importlib.util.spec_from_file_location('bundled_import',Path(__file__).parents[1]/'tools/import_bundled_cloud.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def make_bundle(tmp_path,*,bad=False):
    archive=tmp_path/'sdk.zip';raw=b'\x7fELF\x02synthetic'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('libdhnetsdk.so',raw)
        z.writestr('manifest.json',json.dumps([{'name':'libdhnetsdk.so','sha256':'bad' if bad else hashlib.sha256(raw).hexdigest()}]))
    return archive,raw


def test_fresh_import_and_existing_sdk_is_preserved(tmp_path):
    archive,raw=make_bundle(tmp_path);target=tmp_path/'vendor'
    module.install(archive,target)
    assert (target/'libdhnetsdk.so').read_bytes()==raw
    (target/'libdhnetsdk.so').write_bytes(b'existing installation')
    assert 'preservado' in module.install(archive,target)
    assert (target/'libdhnetsdk.so').read_bytes()==b'existing installation'


def test_bad_payload_does_not_modify_target(tmp_path):
    archive,_=make_bundle(tmp_path,bad=True);target=tmp_path/'vendor'
    with pytest.raises(ValueError,match='Hash'):module.install(archive,target)
    assert not target.exists()

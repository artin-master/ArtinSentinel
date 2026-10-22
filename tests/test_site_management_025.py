from pathlib import Path

import pytest

from artin_sentinel.db import Database
from artin_sentinel.domain import Device


def test_site_archive_restore_and_rename(tmp_path: Path):
    db = Database(tmp_path / 'sentinel.db')
    first = db.list_sites()[0]
    db.update_site(first['id'], 'HomeMaster', 'Casa')
    second_id = db.add_site('Mallet', 'Cliente')

    db.archive_site(second_id, True)
    assert [row['name'] for row in db.list_sites()] == ['HomeMaster']
    assert [row['name'] for row in db.list_archived_sites()] == ['Mallet']

    db.archive_site(second_id, False)
    assert {row['name'] for row in db.list_sites()} == {'HomeMaster', 'Mallet'}
    db.close()


def test_delete_site_can_move_devices_without_losing_them(tmp_path: Path):
    db = Database(tmp_path / 'sentinel.db')
    source = db.list_sites()[0]['id']
    target = db.add_site('Destino')
    device_id = db.upsert_device(Device(site_id=source, name='DVR Casa', ip='192.0.2.10'))

    db.delete_site_permanently(source, target_site_id=target)

    assert db.get_site(source) is None
    moved = db.get_device(device_id)
    assert moved is not None
    assert moved['site_id'] == target
    db.close()


def test_delete_site_requires_explicit_device_decision(tmp_path: Path):
    db = Database(tmp_path / 'sentinel.db')
    site = db.list_sites()[0]['id']
    db.upsert_device(Device(site_id=site, name='Cam', ip='192.0.2.11'))

    with pytest.raises(ValueError):
        db.delete_site_permanently(site)
    db.close()


def test_delete_site_with_devices_cleans_local_records(tmp_path: Path):
    db = Database(tmp_path / 'sentinel.db')
    site = db.list_sites()[0]['id']
    device_id = db.upsert_device(Device(site_id=site, name='Cam', ip='192.0.2.12'))
    db.save_live_workspace(site, 4, [{'device_id': device_id}, {}, {}, {}])

    db.delete_site_permanently(site, delete_devices=True)

    assert db.get_site(site) is None
    assert db.get_device(device_id) is None
    assert db.load_live_workspace(site) is None
    db.close()

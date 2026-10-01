from pathlib import Path

from artin_sentinel.akdb import best_profile, public_summary
from artin_sentinel.db import Database
from artin_sentinel.domain import Device, DeviceKind
from artin_sentinel.providers import pick_provider
from artin_sentinel.recorder import hikvision_channel_url
from artin_sentinel.updater import is_newer, normalize_version


def test_hikvision_channel_urls():
    assert hikvision_channel_url("10.0.0.2", 1, 0).endswith("/Streaming/Channels/101")
    assert hikvision_channel_url("10.0.0.2", 1, 1).endswith("/Streaming/Channels/102")
    assert hikvision_channel_url("10.0.0.2", 18, 0).endswith("/Streaming/Channels/1801")


def test_hikvision_provider_from_service_port():
    d = Device(ip="192.168.1.2", kind=DeviceKind.UNKNOWN, metadata={"open_ports": [80, 554, 8000], "evidence": []})
    pick_provider(d)
    assert d.provider == "hikvision"
    assert d.metadata["akdb_profile"] == "hikvision-generic"


def test_aitek_profile_is_camera_oriented():
    match = best_profile(text="Aitek camera", ports=[80, 554], manufacturer="Aitek")
    assert match is not None
    score, profile = match
    assert profile.provider == "aitek"
    assert profile.device_types == ("camera",)
    assert score >= 70


def test_akdb_contains_field_profiles_without_credentials():
    rows = public_summary()
    assert any(row["provider"] == "intelbras" for row in rows)
    assert any(row["provider"] == "hikvision" for row in rows)
    assert any(row["provider"] == "aitek" for row in rows)
    assert all("password" not in str(row).lower() for row in rows)


def test_device_archive_restore_and_delete(tmp_path: Path):
    db = Database(tmp_path / "s.db")
    site_id = db.list_sites()[0]["id"]
    device_id = db.upsert_device(Device(site_id=site_id, name="DVR Teste", ip="10.0.0.10", kind=DeviceKind.DVR))
    db.archive_device(device_id, True)
    assert db.get_device(device_id)["archived"] == 1
    assert db.list_devices(site_id) == []
    assert len(db.list_archived_devices(site_id)) == 1
    db.archive_device(device_id, False)
    assert len(db.list_devices(site_id)) == 1
    db.delete_device_permanently(device_id)
    assert db.get_device(device_id) is None
    db.close()


def test_ignore_discovery_flag(tmp_path: Path):
    db = Database(tmp_path / "s.db")
    site_id = db.list_sites()[0]["id"]
    device_id = db.upsert_device(Device(site_id=site_id, name="Temporário", ip="10.0.0.11"))
    db.set_ignore_discovery(device_id, True)
    assert db.get_device(device_id)["ignored_discovery"] == 1
    db.close()


def test_version_comparison_for_github_updates():
    assert normalize_version("v0.2.2") == (0, 2, 2)
    assert is_newer("0.2.3", "0.2.2")
    assert not is_newer("0.2.2", "0.2.2")

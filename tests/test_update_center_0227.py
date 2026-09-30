import base64
import json
import os
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from artin_sentinel import __version__
from artin_sentinel.updater import (
    UpdateSettings,
    fetch_update_manifest,
    find_install_root,
    is_newer,
    load_update_settings,
    parse_update_manifest,
    resolve_manifest_url,
    safe_extract_zip,
    save_update_settings,
    sha256_file,
    should_check_on_startup,
    stage_update,
    verify_manifest_signature,
)


def _manifest(package_url: str, sha256: str, size: int = 0, version: str = "0.2.28"):
    return {
        "schema": "artin-update-manifest-v1",
        "app_id": "artin-sentinel",
        "channel": "stable",
        "version": version,
        "title": "Test release",
        "notes": ["A", "B"],
        "package": {"url": package_url, "sha256": sha256, "size": size},
    }


def test_version_0227_and_version_ordering():
    assert __version__ == "0.2.90"
    assert is_newer("0.2.61", __version__)
    assert not is_newer("0.2.30", __version__)
    assert not is_newer("0.2.29", __version__)
    assert not is_newer("0.2.27", __version__)
    assert not is_newer("0.2.26", __version__)


def test_artinupdates_url_resolution():
    assert resolve_manifest_url("https://example.invalid/ArtinUpdates", "stable") == "https://example.invalid/ArtinUpdates/sentinel/stable.json"
    assert resolve_manifest_url("https://example.invalid/sentinel/beta.json", "beta") == "https://example.invalid/sentinel/beta.json"


def test_manifest_requires_correct_app_and_sha():
    payload = _manifest("https://example.invalid/app.zip", "a" * 64)
    m = parse_update_manifest(payload, expected_channel="stable")
    assert m.version == "0.2.28"
    assert m.sha256 == "a" * 64
    bad = dict(payload); bad["app_id"] = "artin-netlens"
    with pytest.raises(ValueError):
        parse_update_manifest(bad, expected_channel="stable")
    bad = _manifest("https://example.invalid/app.zip", "not-a-sha")
    with pytest.raises(ValueError):
        parse_update_manifest(bad, expected_channel="stable")


def test_settings_roundtrip_and_startup_interval(tmp_path):
    s = UpdateSettings(
        manifest_base_url="https://example.invalid/ArtinUpdates",
        channel="beta",
        check_on_startup=True,
        require_signature=False,
        last_checked_at="",
    )
    save_update_settings(tmp_path, s)
    loaded = load_update_settings(tmp_path)
    assert loaded.channel == "beta"
    assert should_check_on_startup(loaded)
    loaded.last_checked_at = datetime.now(timezone.utc).isoformat()
    assert not should_check_on_startup(loaded)
    loaded.last_checked_at = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    assert should_check_on_startup(loaded)


def test_safe_extract_rejects_path_traversal(tmp_path):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as out:
        out.writestr("../escape.txt", "no")
    with pytest.raises(ValueError):
        safe_extract_zip(z, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_stage_update_verifies_sha_and_finds_installer(tmp_path):
    package_root = tmp_path / "package_src" / "ArtinSentinel_test"
    package_root.mkdir(parents=True)
    (package_root / "install.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (package_root / "pyproject.toml").write_text("[project]\nname='artin-sentinel'\n", encoding="utf-8")
    z = tmp_path / "release.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as out:
        for path in package_root.rglob("*"):
            out.write(path, path.relative_to(tmp_path / "package_src"))
    digest = sha256_file(z)
    payload = _manifest(z.as_uri(), digest, z.stat().st_size)
    manifest = parse_update_manifest(payload, expected_channel="stable")
    staged = stage_update(manifest, tmp_path / "data")
    assert Path(staged.helper_path).is_file()
    assert Path(staged.install_root, "install.sh").is_file()
    helper = Path(staged.helper_path).read_text(encoding="utf-8")
    assert "10 s" in helper
    assert "bash ./install.sh" in helper


def test_stage_update_blocks_bad_sha(tmp_path):
    root = tmp_path / "src" / "pkg"; root.mkdir(parents=True)
    (root / "install.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    z = tmp_path / "bad-hash.zip"
    with zipfile.ZipFile(z, "w") as out:
        out.write(root / "install.sh", "pkg/install.sh")
        out.write(root / "pyproject.toml", "pkg/pyproject.toml")
    manifest = parse_update_manifest(_manifest(z.as_uri(), "0" * 64, z.stat().st_size), expected_channel="stable")
    with pytest.raises(ValueError, match="SHA-256"):
        stage_update(manifest, tmp_path / "data")


def test_ui_exposes_update_center_and_coordinated_install():
    source = Path("artin_sentinel/app.py").read_text(encoding="utf-8")
    assert "CENTRO DE ATUALIZAÇÕES" in source
    assert 'self.config_tabs.addTab(tab, "Atualizações")' in source
    assert "Verificar atualizações ao iniciar" in source
    assert "Baixar e instalar" in source
    assert "launch_staged_update(staged, os.getpid())" in source
    assert "QTimer.singleShot(5000, window.check_for_updates_startup)" in source


def test_ed25519_manifest_signature_can_be_verified():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    from artin_sentinel.updater import _canonical_signed_payload

    payload = _manifest("https://example.invalid/app.zip", "b" * 64)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signature = key.sign(_canonical_signed_payload(payload))
    payload["signature"] = {"key_id": "test-key", "value": base64.b64encode(signature).decode("ascii")}
    manifest = parse_update_manifest(payload, expected_channel="stable")
    assert verify_manifest_signature(manifest, {"test-key": base64.b64encode(public).decode("ascii")}) is True

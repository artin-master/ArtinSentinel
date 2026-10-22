import re
import tomllib
from pathlib import Path

from artin_sentinel import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_project_version_matches_package_and_installer():
    metadata_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    match = re.search(r'^NEW_VERSION="([^"]+)"$', installer, re.MULTILINE)
    assert match is not None, 'install.sh não declara NEW_VERSION="..."'
    installer_version = match.group(1)

    versions = {
        "pyproject.toml [project].version": metadata_version,
        "artin_sentinel.__version__": __version__,
        "install.sh NEW_VERSION": installer_version,
    }
    expected = next(iter(versions.values()))
    mismatches = [f"{source}={version}" for source, version in versions.items() if version != expected]
    assert not mismatches, (
        f"Versões do Artin Sentinel divergentes: {', '.join(f'{source}={version}' for source, version in versions.items())}"
    )

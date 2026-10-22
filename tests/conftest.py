"""Release metadata shared by historical feature regression checks."""
from pathlib import Path
import tomllib
import pytest


@pytest.fixture(scope='session')
def release_version():
    root=Path(__file__).resolve().parents[1]
    return tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


@pytest.fixture(scope='session', autouse=True)
def close_retained_playback_sessions():
    yield
    from artin_sentinel.playback_session_pool import shutdown_playback_pool
    shutdown_playback_pool()

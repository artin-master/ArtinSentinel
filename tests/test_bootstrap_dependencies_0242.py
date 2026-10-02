from pathlib import Path

from artin_sentinel import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_version_0242():
    assert __version__ == "0.2.94"


def test_installer_has_real_check_mode_and_supported_package_managers():
    install = (ROOT / "install.sh").read_text()
    assert '--check' in install
    assert 'CHECK_ONLY=1' in install
    assert 'if [[ "$CHECK_ONLY" -eq 1 ]]' in install
    assert 'exit 0' in install
    assert 'dnf' in install
    assert 'apt-get' in install
    assert 'zypper' in install
    assert 'pacman' in install


def test_installer_models_media_dependencies_as_essential():
    install = (ROOT / "install.sh").read_text()
    assert 'print_status ffmpeg ffmpeg 1' in install
    assert 'print_status ffprobe ffprobe 1' in install
    assert 'print_status ffplay ffplay 1' in install
    assert 'p+=(ffmpeg-free)' in install
    assert 'p+=(ffmpeg)' in install


def test_installer_check_precedes_runtime_mutation():
    install = (ROOT / "install.sh").read_text()
    check_pos = install.index('if [[ "$CHECK_ONLY" -eq 1 ]]')
    mkdir_pos = install.index('mkdir -p "$BIN"')
    pip_pos = install.index('pip install --upgrade pip')
    assert check_pos < mkdir_pos
    assert check_pos < pip_pos

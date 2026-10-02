import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def simulate_installer(tmp_path, version, args=(), package_version="0.2.60"):
    runtime = tmp_path / ".local/share/artin-sentinel/runtime/bin"
    runtime.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "pip-called"
    python = runtime / "python"
    python.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = '-c' ]; then printf '%s\\n' '" + version + "'; exit 0; fi\n"
        "touch '" + str(marker) + "'\nexit 1\n"
    )
    python.chmod(0o755)
    script = tmp_path / "install.sh"
    source = (ROOT / "install.sh").read_text()
    source = source.replace('if [[ "${EUID}" -eq 0 ]]; then', 'if false; then', 1)
    source = source.replace('ROOT="$(cd "$(dirname "$0")" && pwd)"', f'ROOT="{ROOT}"', 1)
    source = source.replace('NEW_VERSION="0.2.93"', f'NEW_VERSION="{package_version}"', 1)
    script.write_text(source)
    script.chmod(0o755)
    result = subprocess.run([str(script), *args], capture_output=True, text=True,
                            env={**os.environ, "HOME": str(tmp_path)}, timeout=15)
    return result, marker


def test_old_package_cannot_downgrade_installed_release(tmp_path):
    result, marker = simulate_installer(tmp_path, "0.2.49", package_version="0.2.41")
    assert result.returncode == 1
    assert "0.2.49 já está instalado" in result.stderr
    assert "--allow-downgrade" in result.stderr
    assert not marker.exists()


def test_current_package_cannot_downgrade_future_release(tmp_path):
    result, marker = simulate_installer(tmp_path, "0.2.61")
    assert result.returncode == 1
    assert "0.2.61 já está instalado" in result.stderr
    assert not marker.exists()


def test_check_never_runs_pip_even_when_package_is_older(tmp_path):
    result, marker = simulate_installer(tmp_path, "0.2.49", ("--check",), "0.2.41")
    assert "Versão instalada: 0.2.49; versão deste pacote: 0.2.41" in result.stdout
    assert "Installing collected packages" not in result.stdout
    assert not marker.exists()

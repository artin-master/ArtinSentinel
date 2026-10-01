import subprocess
import sys
import time
from pathlib import Path

from test_installer_downgrade_guard_0253 import simulate_installer


def test_open_sentinel_blocks_noninteractive_upgrade_before_pip_even_with_yes(tmp_path):
    executable = tmp_path / ".local/share/artin-sentinel/runtime/bin/artin-sentinel"
    executable.parent.mkdir(parents=True)
    executable.write_text("import time\ntime.sleep(30)\n")
    running = subprocess.Popen([sys.executable, str(executable)])
    try:
        # Wait until the process has executed the Sentinel entrypoint.
        for _ in range(100):
            try:
                args = Path(f"/proc/{running.pid}/cmdline").read_bytes()
            except OSError:
                args = b""
            if str(executable).encode() in args:
                break
            time.sleep(0.01)
        result, pip_marker = simulate_installer(tmp_path, "0.2.56", ("--yes",))
        assert result.returncode == 3
        assert "Feche o aplicativo" in result.stderr
        assert not pip_marker.exists()
    finally:
        running.terminate()
        running.wait(timeout=5)


def test_check_stays_read_only_even_when_sentinel_is_open(tmp_path):
    executable = tmp_path / ".local/share/artin-sentinel/runtime/bin/artin-sentinel"
    executable.parent.mkdir(parents=True)
    executable.write_text("import time\ntime.sleep(30)\n")
    running = subprocess.Popen([sys.executable, str(executable)])
    try:
        result, pip_marker = simulate_installer(tmp_path, "0.2.56", ("--check",))
        assert "Versão instalada:" in result.stdout
        assert "Feche o aplicativo" not in result.stderr
        assert not pip_marker.exists()
    finally:
        running.terminate()
        running.wait(timeout=5)

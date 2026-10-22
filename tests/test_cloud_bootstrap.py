"""Exercise distribution setup with sandboxed HOME and recorded system commands."""
import os
from pathlib import Path
import subprocess
import pytest


@pytest.mark.parametrize('distribution,like,expected',[
    ('fedora','','dnf install -y wine wine-mono mingw64-win-iconv'),
    ('linuxmint','ubuntu debian','apt-get install -y wine'),
    ('arch','','pacman -S --needed --noconfirm wine wine-mono'),
])
def test_distribution_setup_uses_private_prefix_and_expected_packages(tmp_path,distribution,like,expected):
    source=Path(__file__).parents[1]/'preparar-cloud.sh'
    release=tmp_path/'os-release'
    release.write_text(f'ID={distribution}\nID_LIKE="{like}"\nPRETTY_NAME="Test Linux"\n')
    text=source.read_text().replace('/etc/os-release',str(release))
    # The production root guard stays intact; remove it only for this isolated fixture.
    text='\n'.join(line for line in text.splitlines() if 'if [[ "$EUID" -eq 0 ]]' not in line)
    script=tmp_path/'preparar-cloud.sh';script.write_text(text)
    bin_dir=tmp_path/'bin';bin_dir.mkdir()
    def command(name,body):
        file=bin_dir/name;file.write_text('#!/bin/sh\n'+body);file.chmod(0o755)
    command('sudo','printf "%s\\n" "$*" >> "$HOME/commands"\n')
    command('wine','[ "$1" != --version ] || echo wine-9.0\nprintf "%s\\n" "$WINEPREFIX" >> "$HOME/prefixes"\n')
    command('wineboot','printf "%s\\n" "$WINEPREFIX" >> "$HOME/prefixes"\n')
    command('winepath','exit 0\n')
    runtime=tmp_path/'.local/share/artin-sentinel/runtime/bin';runtime.mkdir(parents=True)
    python=runtime/'python';python.write_text('#!/bin/sh\nexit 0\n');python.chmod(0o755)
    env=dict(os.environ,HOME=str(tmp_path),PATH=str(bin_dir)+':'+os.environ['PATH'])
    result=subprocess.run(['bash',str(script),'--yes'],env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    assert expected in (tmp_path/'commands').read_text().splitlines()
    assert set((tmp_path/'prefixes').read_text().splitlines())=={str(tmp_path/'.local/share/artin-sentinel/wine-cloud')}

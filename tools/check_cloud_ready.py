"""Read-only installer check. Never starts Wine, a tunnel, or a DVR connection."""
import shutil


def cloud_ready(*, manager=None, which=shutil.which):
    if not which('wine') or not which('winepath'):
        return False
    if manager is None:
        from artin_sentinel.intelbras_wine import wine_manager
        manager = wine_manager()
    compiler = manager.prefix / 'drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    try:
        return compiler.is_file() and manager.installed()
    except (OSError, ValueError, KeyError, TypeError):
        return False


if __name__ == '__main__':
    raise SystemExit(0 if cloud_ready() else 1)

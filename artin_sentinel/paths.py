from pathlib import Path
import os

def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    path = base / "artin-sentinel"
    path.mkdir(parents=True, exist_ok=True)
    return path

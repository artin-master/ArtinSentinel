"""Bounded, sanitized diagnostics for the equipment panel."""

from pathlib import Path
import re

from .live import sanitize_text


def sanitize_log_text(value: object) -> str:
    text = sanitize_text(str(value or ""))
    text = re.sub(r"(?im)\b(senha|password|passwd|token|api[_-]?key|secret)\s*[:=]\s*[^\s,;]+", r"\1=<oculto>", text)
    return text


def read_log_tail(log_dir: Path, source: str, *, max_bytes: int = 131072, max_lines: int = 450) -> str:
    """Read only recognized application logs; never load a whole growing file."""
    log_dir = Path(log_dir)
    if source == "rtsp":
        path = log_dir / "rtsp-diagnostics.log"
    elif source == "fault":
        path = log_dir / "native-fault.log"
    elif source == "update":
        path = max(log_dir.glob("update-*.log"), key=lambda p: p.stat().st_mtime, default=None) if log_dir.is_dir() else None
    else:
        raise ValueError("Fonte de log não reconhecida")
    if path is None or not path.is_file():
        return "Ainda não há registros nesta fonte."
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - max_bytes))
            data = stream.read(max_bytes)
        if size > max_bytes:
            data = data.split(b"\n", 1)[-1]
        return sanitize_log_text("\n".join(data.decode("utf-8", "replace").splitlines()[-max_lines:]))
    except OSError as exc:
        return f"Não foi possível ler o registro: {sanitize_log_text(exc)}"


def filter_log_lines(contents: str, query: str) -> str:
    query = query.strip().casefold()
    return contents if not query else "\n".join(line for line in contents.splitlines() if query in line.casefold())

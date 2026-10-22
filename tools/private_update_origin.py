#!/usr/bin/env python3
"""Local update origin. Expose ONLY through a trusted HTTPS reverse proxy."""

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import zipfile


def _atomic_bytes(path: Path, data: bytes, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as handle:
        temp = Path(handle.name)
        os.chmod(temp, mode)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _clients(root: Path) -> dict:
    path = root / "clients.json"
    return json.loads(path.read_text()) if path.exists() else {}


def issue_client(root: Path, name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", name):
        raise ValueError("Nome do cliente inválido")
    clients = _clients(root)
    if name in clients:
        raise ValueError("Cliente já existe; revogue antes de emitir outra chave")
    token = secrets.token_urlsafe(36)
    salt = secrets.token_hex(16)
    clients[name] = {"salt": salt, "digest": hashlib.sha256((salt + token).encode()).hexdigest(), "active": True}
    _atomic_bytes(root / "clients.json", (json.dumps(clients, indent=2) + "\n").encode())
    return token


def revoke_client(root: Path, name: str):
    clients = _clients(root)
    if name not in clients:
        raise ValueError("Cliente desconhecido")
    clients[name]["active"] = False
    _atomic_bytes(root / "clients.json", (json.dumps(clients, indent=2) + "\n").encode())


def authorized(root: Path, token: str) -> bool:
    if not token or len(token) > 256:
        return False
    for row in _clients(root).values():
        digest = hashlib.sha256((row["salt"] + token).encode()).hexdigest()
        if hmac.compare_digest(digest, row["digest"]) and row["active"]:
            return True
    return False


def publish_local(root: Path, archive: Path, base_url: str, channel="stable") -> dict:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use uma URL base HTTPS sem credenciais")
    if channel not in ("stable", "beta"):
        raise ValueError("Canal inválido")
    archive = Path(archive)
    if not re.fullmatch(r"ArtinSentinel_[0-9A-Za-z_.-]+\.zip", archive.name):
        raise ValueError("Nome do pacote inválido")
    with zipfile.ZipFile(archive) as z:
        matches = [name for name in z.namelist() if name.endswith("/artin_sentinel/__init__.py")]
        if len(matches) != 1 or z.testzip() is not None:
            raise ValueError("ZIP do Sentinel inválido")
        match = re.search(r'__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', z.read(matches[0]).decode())
        if not match:
            raise ValueError("Versão não encontrada no pacote")
        version = match.group(1)
    data = archive.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    target = root / "packages" / archive.name
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError("Um pacote com esse nome já existe com conteúdo diferente")
    if not target.exists():
        _atomic_bytes(target, data)
    manifest = {
        "schema": "artin-update-manifest-v1", "app_id": "artin-sentinel", "channel": channel,
        "version": version, "title": f"Artin Sentinel {version}", "notes": "Atualização privada do Sentinel.",
        "package": {"url": base_url.rstrip("/") + "/packages/" + archive.name,
                    "sha256": digest, "size": len(data)},
    }
    _atomic_bytes(root / "sentinel" / f"{channel}.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    return manifest


def handler_for(root: Path):
    root = Path(root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or not authorized(root, header[7:]):
                self.send_error(401, "Acesso não autorizado")
                return
            route = self.path
            if route in ("/sentinel/stable.json", "/sentinel/beta.json"):
                target = root / route.lstrip("/")
                kind = "application/json"
            elif re.fullmatch(r"/packages/ArtinSentinel_[0-9A-Za-z_.-]+\.zip", route):
                target = root / route.lstrip("/")
                kind = "application/zip"
            else:
                self.send_error(404)
                return
            if not target.is_file() or target.is_symlink():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                with target.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            # Authorization headers never enter access logs.
            super().log_message(format, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Origem local de atualizações Artin Sentinel")
    parser.add_argument("--root", type=Path, default=Path.home() / ".local/share/artin-update-origin")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("serve").add_argument("--port", type=int, default=18888)
    sub.add_parser("issue").add_argument("name")
    sub.add_parser("revoke").add_argument("name")
    pub = sub.add_parser("publish")
    pub.add_argument("zip", type=Path)
    pub.add_argument("--base-url", required=True)
    pub.add_argument("--channel", default="stable", choices=("stable", "beta"))
    args = parser.parse_args()
    args.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.mode == "issue":
        print("Chave do cliente (copie uma vez):", issue_client(args.root, args.name))
    elif args.mode == "revoke":
        revoke_client(args.root, args.name)
        print("Acesso revogado:", args.name)
    elif args.mode == "publish":
        result = publish_local(args.root, args.zip, args.base_url, args.channel)
        print("Pacote privado preparado:", result["version"], result["package"]["sha256"])
    else:
        print("Origem acessível somente em 127.0.0.1; coloque HTTPS autenticado à frente.")
        ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(args.root)).serve_forever()


if __name__ == "__main__":
    main()

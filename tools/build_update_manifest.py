#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

SCHEMA = "artin-update-manifest-v1"
APP_ID = "artin-sentinel"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_payload(payload: dict) -> bytes:
    clean = dict(payload)
    clean.pop("signature", None)
    return json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_private_key(args) -> bytes | None:
    value = ""
    if args.private_key_file:
        value = Path(args.private_key_file).read_text(encoding="utf-8").strip()
    elif os.environ.get("ARTIN_UPDATE_ED25519_PRIVATE_KEY_B64"):
        value = os.environ["ARTIN_UPDATE_ED25519_PRIVATE_KEY_B64"].strip()
    return base64.b64decode(value) if value else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Artin Sentinel ArtinUpdates manifest")
    ap.add_argument("package", type=Path)
    ap.add_argument("--version", required=True)
    ap.add_argument("--package-url", required=True)
    ap.add_argument("--channel", choices=["stable", "beta"], default="stable")
    ap.add_argument("--title", default="")
    ap.add_argument("--release-url", default="")
    ap.add_argument("--notes-file")
    ap.add_argument("--published-at", default="")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--key-id", default="")
    ap.add_argument("--private-key-file", help="arquivo contendo chave privada Ed25519 raw em base64")
    args = ap.parse_args()

    package = args.package.resolve()
    if not package.is_file():
        raise SystemExit(f"Pacote não encontrado: {package}")
    notes: list[str] = []
    if args.notes_file:
        notes = [line.strip(" •\t") for line in Path(args.notes_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {
        "schema": SCHEMA,
        "app_id": APP_ID,
        "channel": args.channel,
        "version": args.version.lstrip("vV"),
        "title": args.title or f"Artin Sentinel {args.version.lstrip('vV')}",
        "notes": notes,
        "published_at": args.published_at,
        "release_url": args.release_url,
        "package": {
            "url": args.package_url,
            "sha256": sha256_file(package),
            "size": package.stat().st_size,
        },
    }
    private_key = read_private_key(args)
    if private_key:
        if not args.key_id:
            raise SystemExit("--key-id é obrigatório quando o manifesto é assinado")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        if len(private_key) != 32:
            raise SystemExit("A chave privada Ed25519 raw deve ter 32 bytes")
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(canonical_payload(payload))
        payload["signature"] = {
            "key_id": args.key_id,
            "value": base64.b64encode(signature).decode("ascii"),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    print(payload["package"]["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

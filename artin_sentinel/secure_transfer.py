"""Encrypted portability helpers for credential-bearing Sentinel transfers.

Plain inventory JSON remains supported. When credentials are included, the entire
payload is encrypted with a user-supplied transfer password; device passwords
never appear as plaintext in the export file, logs, SQLite, argv or environment.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

FORMAT = "artin-sentinel-secure-transfer-v1"
AAD = b"Artin Sentinel secure transfer v1"
MAX_PASSPHRASE = 512


class SecureTransferError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise SecureTransferError("Pacote criptografado inválido.") from exc


def _derive(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or not passphrase or len(passphrase) > MAX_PASSPHRASE:
        raise SecureTransferError("Senha de transferência inválida.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt_bundle(payload: dict, credentials: dict, passphrase: str) -> bytes:
    """Encrypt inventory + credential map as one authenticated envelope."""
    if not isinstance(payload, dict) or not isinstance(credentials, dict):
        raise SecureTransferError("Dados de transferência inválidos.")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive(passphrase, salt)
    body = json.dumps(
        {"payload": payload, "credentials": credentials},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, body, AAD)
    envelope = {
        "format": FORMAT,
        "kdf": "scrypt-n32768-r8-p1",
        "cipher": "aes-256-gcm",
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def is_secure_bundle(raw: bytes) -> bool:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception:
        return False
    return isinstance(data, dict) and data.get("format") == FORMAT


def decrypt_bundle(raw: bytes, passphrase: str) -> tuple[dict, dict]:
    try:
        envelope = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise SecureTransferError("Pacote criptografado inválido.") from exc
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT:
        raise SecureTransferError("Formato seguro do Sentinel não reconhecido.")
    if envelope.get("kdf") != "scrypt-n32768-r8-p1" or envelope.get("cipher") != "aes-256-gcm":
        raise SecureTransferError("Algoritmo de proteção não suportado.")
    salt = _unb64(str(envelope.get("salt") or ""))
    nonce = _unb64(str(envelope.get("nonce") or ""))
    ciphertext = _unb64(str(envelope.get("ciphertext") or ""))
    if len(salt) != 16 or len(nonce) != 12 or len(ciphertext) < 16:
        raise SecureTransferError("Pacote criptografado inválido.")
    try:
        plaintext = AESGCM(_derive(passphrase, salt)).decrypt(nonce, ciphertext, AAD)
        decoded = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise SecureTransferError("Senha de transferência incorreta ou arquivo alterado.") from exc
    if not isinstance(decoded, dict):
        raise SecureTransferError("Conteúdo criptografado inválido.")
    payload = decoded.get("payload")
    credentials = decoded.get("credentials", {})
    if not isinstance(payload, dict) or not isinstance(credentials, dict):
        raise SecureTransferError("Conteúdo criptografado inválido.")
    return payload, credentials


def credential_key(site_name: str, ip: str) -> str:
    """Stable non-secret key used only inside the encrypted body."""
    return f"{str(site_name).strip().casefold()}\x1f{str(ip).strip().casefold()}"


def collect_credentials(owner, payload: dict) -> tuple[dict, list[str]]:
    """Read only credentials currently available to this Sentinel session/keyring."""
    result: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    sites = payload.get("sites", []) if isinstance(payload, dict) else []
    # Resolve by Site + endpoint to avoid leaking internal DB ids into portable files.
    for site in sites:
        site_name = str(site.get("name") or "")
        for exported in site.get("devices", []):
            ip = str(exported.get("ip") or "")
            matches = [
                d for d in owner.db.list_devices(None)
                if int(d["site_id"] or 0) in {int(s["id"]) for s in owner.db.list_sites() if str(s["name"]).casefold() == site_name.casefold()}
                and str(d["ip"] or "").casefold() == ip.casefold()
            ]
            if len(matches) != 1:
                missing.append(f"{site_name} • {exported.get('name') or ip}")
                continue
            device = matches[0]
            device_id = int(device["id"])
            credentials = owner.session_credentials.get(device_id)
            if credentials is None and bool(device["credential_saved"]):
                secret = owner.credential_store.get_password(device_id)
                if secret is not None:
                    credentials = (str(device["credential_username"] or "admin"), secret)
            if not credentials or not credentials[1]:
                missing.append(f"{site_name} • {device['name'] or ip}")
                continue
            result[credential_key(site_name, ip)] = {
                "username": str(credentials[0] or "admin"),
                "password": str(credentials[1]),
            }
    return result, missing


def restore_credentials(owner, payload: dict, credentials: dict, preview: dict) -> dict:
    """Restore secrets only into resolved non-conflicting device records."""
    rows = preview.get("rows", []) if isinstance(preview, dict) else []
    restored = skipped = 0
    by_key = {}
    for row in rows:
        if row.get("status") == "existing" and row.get("target_device_id") is not None:
            by_key[(str(row.get("site") or "").casefold(), str(row.get("ip") or "").casefold())] = int(row["target_device_id"])
    for site in payload.get("sites", []):
        site_name = str(site.get("name") or "")
        for dev in site.get("devices", []):
            ip = str(dev.get("ip") or "")
            secret = credentials.get(credential_key(site_name, ip))
            device_id = by_key.get((site_name.casefold(), ip.casefold()))
            if not isinstance(secret, dict) or device_id is None:
                skipped += 1
                continue
            username = str(secret.get("username") or "admin")
            password = str(secret.get("password") or "")
            if not password:
                skipped += 1
                continue
            owner.session_credentials[device_id] = (username, password)
            saved = owner.credential_store.set_password(device_id, password)
            owner.db.update_device_credential_meta(device_id, username, saved.ok)
            restored += 1
    return {"restored": restored, "skipped": skipped}

"""Local application access PIN/password verifier; never stores plaintext."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile

ITERATIONS = 600_000


class AppAuth:
    def __init__(self, path: Path):
        self.path = Path(path)

    @property
    def configured(self) -> bool:
        return self.path.exists()

    def verify(self, password: str) -> bool:
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record,dict):return False
            if record.get("version") != 1 or record.get("algorithm") != "pbkdf2-sha256":
                return False
            iterations = int(record["iterations"])
            if not 100_000 <= iterations <= 2_000_000:
                return False
            salt = bytes.fromhex(record["salt"])
            expected = bytes.fromhex(record["verifier"])
            if len(salt) != 32 or len(expected) != 32:
                return False
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(actual, expected)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            return False

    def set_password(self, password: str) -> None:
        if len(password) < 4:
            raise ValueError("Use pelo menos 4 caracteres.")
        salt = os.urandom(32)
        verifier = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
        record = {"version": 1, "algorithm": "pbkdf2-sha256", "iterations": ITERATIONS,
                  "salt": salt.hex(), "verifier": verifier.hex()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".access-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(record, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

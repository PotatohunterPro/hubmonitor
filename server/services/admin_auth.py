"""Autenticacao local para a area de configuracao do servidor."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

PASSWORD_ITERATIONS = 600_000
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60


def _restrict_file(path: Path) -> None:
    if os.name == "nt":
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                "*S-1-5-18:(F)",
                "*S-1-5-32-544:(F)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        path.chmod(0o600)


def _write_restricted_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        _restrict_file(temporary)
        os.replace(temporary, path)
        _restrict_file(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class AdminAuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def configured(self) -> bool:
        return self.path.is_file()

    def create_password(self, password: str) -> None:
        if len(password) < 12:
            raise ValueError("Use uma senha com pelo menos 12 caracteres.")
        if self.configured:
            raise FileExistsError("A senha administrativa ja foi configurada.")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        )
        _write_restricted_json(
            self.path,
            {
                "version": 1,
                "iterations": PASSWORD_ITERATIONS,
                "salt": base64.b64encode(salt).decode("ascii"),
                "digest": base64.b64encode(digest).decode("ascii"),
            },
        )

    def verify_password(self, password: str) -> bool:
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if record.get("version") != 1:
                return False
            salt = base64.b64decode(record["salt"], validate=True)
            expected = base64.b64decode(record["digest"], validate=True)
            iterations = int(record["iterations"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)


def issue_session(secret: bytes, now: int | None = None) -> str:
    expires = (now if now is not None else int(time.time())) + SESSION_MAX_AGE_SECONDS
    payload = f"{expires}.{secrets.token_urlsafe(18)}".encode("ascii")
    signature = hmac.new(secret, payload, hashlib.sha256).digest()
    return ".".join(
        (
            base64.urlsafe_b64encode(payload).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
        )
    )


def valid_session(secret: bytes, value: str | None, now: int | None = None) -> bool:
    if not value:
        return False
    try:
        encoded_payload, encoded_signature = value.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
        signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        expires_text, nonce = payload.decode("ascii").split(".", 1)
        expires = int(expires_text)
        if not nonce or expires < (now if now is not None else int(time.time())):
            return False
    except (ValueError, UnicodeDecodeError):
        return False
    expected = hmac.new(secret, payload, hashlib.sha256).digest()
    return hmac.compare_digest(signature, expected)

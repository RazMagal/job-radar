"""Keeps the applied-jobs log private in a public repo.

Where you've applied is nobody's business, but the log is worth keeping in git for
backup and history. So the plaintext never touches disk once a key exists: the log
lives only as `data/applied.json.enc`, read into memory and written straight back.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from `cryptography`, which is already a
dependency, rather than `age`/`gpg` — no system package to install locally or in CI.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

KEY_ENV = "JOBRADAR_KEY"
KEY_FILE_ENV = "JOBRADAR_KEY_FILE"
DEFAULT_KEY_FILE = Path.home() / ".config" / "job-radar" / "key"


class VaultError(RuntimeError):
    pass


def _fernet(key: bytes):
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise VaultError(
            "encryption needs the `cryptography` package: pip install -r requirements.txt"
        ) from None
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise VaultError(f"malformed key: {exc}") from None


def key_path() -> Path:
    return Path(os.environ.get(KEY_FILE_ENV) or DEFAULT_KEY_FILE)


def load_key() -> bytes | None:
    """Key from $JOBRADAR_KEY (how CI gets it), else the key file. None = not set up."""
    raw = os.environ.get(KEY_ENV)
    if raw:
        return raw.strip().encode()
    path = key_path()
    if path.exists():
        return path.read_text(encoding="utf-8").strip().encode()
    return None


def generate_key() -> bytes:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise VaultError(
            "encryption needs the `cryptography` package: pip install -r requirements.txt"
        ) from None
    return Fernet.generate_key()


def save_key(key: bytes, path: Path | None = None) -> Path:
    path = Path(path or key_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key + b"\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600 — it's the only copy
    return path


def encrypt(data: bytes, key: bytes) -> bytes:
    return _fernet(key).encrypt(data)


def decrypt(blob: bytes, key: bytes) -> bytes:
    from cryptography.fernet import InvalidToken

    try:
        return _fernet(key).decrypt(blob)
    except InvalidToken:
        raise VaultError(
            "cannot decrypt the applied log — wrong key. The log is unreadable without "
            "the key it was encrypted with; restore that key rather than deleting the file."
        ) from None

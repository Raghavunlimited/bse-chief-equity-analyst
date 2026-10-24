"""Encrypt secrets at rest (LLM API keys). Never log plaintext."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def get_fernet() -> Fernet:
    raw = (os.getenv("LLM_FERNET_KEY") or "").strip()
    if raw:
        try:
            return Fernet(raw.encode("utf-8") if isinstance(raw, str) else raw)
        except Exception:
            logger.warning("Invalid LLM_FERNET_KEY; deriving from SECRET_KEY")
    secret = (os.getenv("SECRET_KEY") or "dev-only-change-me-swing-desk-32c").strip()
    return Fernet(_derive_fernet_key(secret))


def encrypt_secret(plaintext: str) -> str:
    token = get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret") from exc


def redact(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "***"
    return f"{value[:keep]}…***"

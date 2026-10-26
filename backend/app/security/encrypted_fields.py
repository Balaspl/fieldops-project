"""Authenticated field encryption backed by an externally supplied key."""

from __future__ import annotations

import base64
import os
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


_PREFIX = "enc:v1:"


def _derived_key(info: bytes, length: int, key_material: str | None = None) -> bytes:
    raw = (
        key_material if key_material is not None else os.getenv("DATA_ENCRYPTION_KEY", "")
    ).strip().encode("utf-8")
    if not raw:
        raise RuntimeError("DATA_ENCRYPTION_KEY is not configured")
    if len(raw) < 32:
        raise RuntimeError("DATA_ENCRYPTION_KEY is invalid")
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(raw)


def is_encrypted(value: str) -> bool:
    return value.startswith(_PREFIX)


def encrypt_at_rest(
    value: str,
    context: str,
    *,
    searchable: bool = False,
    key_material: str | None = None,
) -> str:
    """Encrypt one value with context-bound authenticated encryption."""
    aad = [context.encode("utf-8")]
    if searchable:
        ciphertext = AESSIV(_derived_key(b"fieldops/searchable/v1", 64, key_material)).encrypt(
            value.encode("utf-8"), aad
        )
        mode = "s"
    else:
        nonce = secrets.token_bytes(12)
        ciphertext = nonce + AESGCM(
            _derived_key(b"fieldops/randomized/v1", 32, key_material)
        ).encrypt(nonce, value.encode("utf-8"), context.encode("utf-8"))
        mode = "r"
    return _PREFIX + mode + ":" + base64.urlsafe_b64encode(ciphertext).decode("ascii")


def decrypt_at_rest(value: str, context: str, *, key_material: str | None = None) -> str:
    """Decrypt a field, failing closed on missing/wrong keys or tampering."""
    if not value.startswith(_PREFIX):
        raise RuntimeError("Sensitive field is not encrypted")
    try:
        mode, encoded = value[len(_PREFIX):].split(":", 1)
        ciphertext = base64.urlsafe_b64decode(encoded.encode("ascii"))
        if mode == "s":
            plaintext = AESSIV(_derived_key(b"fieldops/searchable/v1", 64, key_material)).decrypt(
                ciphertext, [context.encode("utf-8")]
            )
        elif mode == "r":
            nonce, payload = ciphertext[:12], ciphertext[12:]
            plaintext = AESGCM(_derived_key(b"fieldops/randomized/v1", 32, key_material)).decrypt(
                nonce, payload, context.encode("utf-8")
            )
        else:
            raise ValueError
        return plaintext.decode("utf-8")
    except (ValueError, UnicodeError, InvalidTag, TypeError):
        raise RuntimeError("Encrypted field could not be decrypted") from None


def reencrypt_at_rest(
    value: str,
    context: str,
    *,
    searchable: bool,
    old_key: str,
    new_key: str,
) -> str:
    """Re-encrypt a stored value during controlled key rotation."""
    plaintext = decrypt_at_rest(value, context, key_material=old_key)
    return encrypt_at_rest(
        plaintext,
        context,
        searchable=searchable,
        key_material=new_key,
    )


class EncryptedText(TypeDecorator[str]):
    """SQLAlchemy text field encrypted on write and decrypted on read."""

    impl = Text
    cache_ok = True

    def __init__(self, context: str, *, searchable: bool = False) -> None:
        self.context = context
        self.searchable = searchable
        super().__init__()

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return encrypt_at_rest(str(value), self.context, searchable=self.searchable)

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return decrypt_at_rest(str(value), self.context)

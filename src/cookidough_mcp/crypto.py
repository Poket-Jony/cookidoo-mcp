"""AES-256-GCM credential encryption and token helpers for the http transport."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import uuid
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from pydantic import SecretStr

_IV_LENGTH_BYTES = 12


def _key_bytes(encryption_key: SecretStr) -> bytes:
    hex_key = encryption_key.get_secret_value()
    key = bytes.fromhex(hex_key)
    if len(key) != 32:
        raise ValueError("encryption_key must be exactly 32 bytes (64 hex characters).")
    return key


def encrypt_secret(plaintext: str, encryption_key: SecretStr) -> str:
    """Encrypt ``plaintext``; returns ``iv.ciphertext`` (both base64, AESGCM tag included)."""
    key = _key_bytes(encryption_key)
    iv = os.urandom(_IV_LENGTH_BYTES)
    ciphertext = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return f"{base64.b64encode(iv).decode()}.{base64.b64encode(ciphertext).decode()}"


def decrypt_secret(payload: str, encryption_key: SecretStr) -> str:
    """Reverse `encrypt_secret`."""
    key = _key_bytes(encryption_key)
    iv_b64, _, ciphertext_b64 = payload.partition(".")
    if not iv_b64 or not ciphertext_b64:
        raise ValueError("Malformed encrypted payload.")
    iv = base64.b64decode(iv_b64)
    ciphertext = base64.b64decode(ciphertext_b64)
    return AESGCM(key).decrypt(iv, ciphertext, None).decode("utf-8")


def random_token(num_bytes: int = 32) -> str:
    return secrets.token_urlsafe(num_bytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_id() -> str:
    return str(uuid.uuid4())

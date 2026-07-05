"""Tests for AES-256-GCM credential encryption and token helpers."""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr

from cookidough_mcp.crypto import (
    decrypt_secret,
    encrypt_secret,
    new_id,
    random_token,
    sha256_hex,
)

_KEY = SecretStr("00" * 32)


def test_encrypt_decrypt_round_trips() -> None:
    encrypted = encrypt_secret("hunter2", _KEY)
    assert decrypt_secret(encrypted, _KEY) == "hunter2"


def test_encrypt_output_does_not_contain_plaintext() -> None:
    encrypted = encrypt_secret("super-secret-password", _KEY)
    assert "super-secret-password" not in encrypted


def test_encrypt_is_randomized() -> None:
    assert encrypt_secret("hunter2", _KEY) != encrypt_secret("hunter2", _KEY)


def test_decrypt_fails_with_wrong_key() -> None:
    encrypted = encrypt_secret("hunter2", _KEY)
    wrong_key = SecretStr("11" * 32)
    with pytest.raises(InvalidTag):
        decrypt_secret(encrypted, wrong_key)


def test_encrypt_rejects_short_key() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_secret("hunter2", SecretStr("00"))


def test_decrypt_rejects_malformed_payload() -> None:
    with pytest.raises(ValueError, match="Malformed"):
        decrypt_secret("not-a-valid-payload", _KEY)


def test_random_token_is_unique_and_urlsafe() -> None:
    tokens = {random_token() for _ in range(20)}
    assert len(tokens) == 20
    assert all(all(c.isalnum() or c in "-_" for c in token) for token in tokens)


def test_sha256_hex_is_deterministic() -> None:
    assert sha256_hex("value") == sha256_hex("value")
    assert sha256_hex("value") != sha256_hex("other")


def test_new_id_is_unique() -> None:
    assert new_id() != new_id()

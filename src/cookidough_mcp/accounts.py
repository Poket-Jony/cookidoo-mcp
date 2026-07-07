"""Cookidoo account store: encrypted credentials for the http transport.

One row per Cookidoo email, independent of how many OAuth clients (Claude.ai
connectors, MCP Inspector, ...) end up issuing tokens tied to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .crypto import decrypt_secret, encrypt_secret, new_id

if TYPE_CHECKING:
    from pydantic import SecretStr

    from .db import LazyPool


@dataclass(frozen=True)
class CookidoughAccount:
    """A stored Cookidoo account: decrypted, for in-process use only."""

    id: str
    email: str
    password: str


async def upsert_account(
    lazy_pool: LazyPool, email: str, password: str, encryption_key: SecretStr
) -> CookidoughAccount:
    """Insert or refresh the stored credentials for ``email``; returns the account."""
    normalized_email = email.strip().lower()
    encrypted_password = encrypt_secret(password, encryption_key)
    account_id = new_id()
    pool = await lazy_pool.get()
    row = await pool.fetchrow(
        """
        INSERT INTO cookidough_accounts (id, email, encrypted_password)
        VALUES ($1, $2, $3)
        ON CONFLICT (email)
        DO UPDATE SET encrypted_password = EXCLUDED.encrypted_password, updated_at = now()
        RETURNING id, email
        """,
        account_id,
        normalized_email,
        encrypted_password,
    )
    assert row is not None
    return CookidoughAccount(id=row["id"], email=row["email"], password=password)


async def get_account_by_id(
    lazy_pool: LazyPool, account_id: str, encryption_key: SecretStr
) -> CookidoughAccount | None:
    pool = await lazy_pool.get()
    row = await pool.fetchrow(
        "SELECT id, email, encrypted_password FROM cookidough_accounts WHERE id = $1",
        account_id,
    )
    if row is None:
        return None
    return CookidoughAccount(
        id=row["id"],
        email=row["email"],
        password=decrypt_secret(row["encrypted_password"], encryption_key),
    )

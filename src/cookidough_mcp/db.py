"""Postgres pool + migrations for the http transport's OAuth persistence."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from importlib import resources
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from .config import Settings

_LOGGER = logging.getLogger(__name__)
_CLEANUP_INTERVAL_SECONDS = 60 * 60


async def create_pool(settings: Settings) -> asyncpg.Pool:
    """Create the connection pool used by the OAuth provider and account store."""
    if settings.database_url is None:
        raise ValueError("database_url must be set to create a pool.")
    return await asyncpg.create_pool(dsn=settings.database_url)


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply the (idempotent) schema migration."""
    sql = resources.files("cookidough_mcp.migrations").joinpath("001_init.sql").read_text()
    async with pool.acquire() as connection:
        await connection.execute(sql)


async def _delete_expired(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute("DELETE FROM oauth_codes WHERE expires_at < now()")
        await connection.execute(
            "DELETE FROM oauth_tokens WHERE "
            "(refresh_token_hash IS NULL AND access_token_expires_at < now()) OR "
            "(refresh_token_expires_at IS NOT NULL AND refresh_token_expires_at < now()) OR "
            "revoked_at < now() - interval '1 day'"
        )


async def _cleanup_loop(pool: asyncpg.Pool) -> None:
    while True:
        try:
            await _delete_expired(pool)
        except asyncpg.PostgresError:
            _LOGGER.exception("OAuth cleanup sweep failed; will retry next interval.")
        await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)


def start_cleanup_task(pool: asyncpg.Pool) -> asyncio.Task[None]:
    """Start the background sweep that deletes expired codes/tokens.

    Runs alongside lazy expiry checks in the OAuth provider itself, so a
    missed or delayed sweep never makes an expired code/token usable.
    """
    return asyncio.create_task(_cleanup_loop(pool))


async def stop_cleanup_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

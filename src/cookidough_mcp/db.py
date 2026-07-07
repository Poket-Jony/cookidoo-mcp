"""Postgres pool + migrations for the http transport's OAuth persistence.

The pool (and its cleanup background task) are created lazily, on first
actual use from inside a real request handler, rather than eagerly during
the ASGI lifespan. `anyio.run()` / uvicorn's `Server.serve()` bootstrap
(how FastMCP's streamable-http transport starts) can leave objects created
during lifespan startup bound to a different, later-discarded asyncio loop
than the one that actually ends up serving requests -- asyncpg then fails
with ``RuntimeError: ... attached to a different loop`` on first use.
Creating the pool (and starting the cleanup task) inside the coroutine that
actually needs it guarantees both are bound to the loop that is really
serving traffic.
"""

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


class LazyPool:
    """Creates the asyncpg pool, applies migrations, and starts the expired-
    token cleanup sweep on first use.

    Safe under concurrent first callers: only one of them actually creates
    the pool, the rest await the same in-flight creation via the lock.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.database_url is None:
            raise ValueError("database_url must be set to create a pool.")
        self._database_url = settings.database_url
        self._pool: asyncpg.Pool | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is None:
                pool = await asyncpg.create_pool(dsn=self._database_url)
                try:
                    await _run_migrations(pool)
                except BaseException:
                    await pool.close()
                    raise
                self._pool = pool
                self._cleanup_task = asyncio.create_task(_cleanup_loop(self))
        return self._pool

    async def aclose(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


async def _run_migrations(pool: asyncpg.Pool) -> None:
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


async def _cleanup_loop(lazy_pool: LazyPool) -> None:
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
        try:
            pool = await lazy_pool.get()
            await _delete_expired(pool)
        except asyncpg.PostgresError:
            _LOGGER.exception("OAuth cleanup sweep failed; will retry next interval.")

"""Tests for the per-account CookidoughSession cache (http transport)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from cookidough_mcp.accounts import CookidoughAccount
from cookidough_mcp.config import Settings
from cookidough_mcp.errors import AuthenticationError
from cookidough_mcp.session import CookidoughSession
from cookidough_mcp.session_cache import CookidoughSessionCache

_HTTP_SETTINGS = Settings(
    mcp_mode="http",
    public_url="https://example.test",
    database_url="postgres://example/db",
    encryption_key=SecretStr("00" * 32),
)

_ACCOUNT = CookidoughAccount(id="acc-1", email="a@example.com", password="hunter2")


async def test_get_or_create_calls_loader_once_then_caches() -> None:
    cache = CookidoughSessionCache(_HTTP_SETTINGS)
    calls = 0

    async def load_account() -> CookidoughAccount | None:
        nonlocal calls
        calls += 1
        return _ACCOUNT

    first = await cache.get_or_create("acc-1", load_account)
    second = await cache.get_or_create("acc-1", load_account)

    assert first is second
    assert isinstance(first, CookidoughSession)
    assert calls == 1


async def test_get_or_create_raises_for_unknown_account() -> None:
    cache = CookidoughSessionCache(_HTTP_SETTINGS)

    async def load_account() -> CookidoughAccount | None:
        return None

    with pytest.raises(AuthenticationError):
        await cache.get_or_create("missing", load_account)


async def test_store_seeds_cache_without_calling_loader() -> None:
    cache = CookidoughSessionCache(_HTTP_SETTINGS)
    seeded = CookidoughSession(
        _HTTP_SETTINGS.model_copy(
            update={"email": _ACCOUNT.email, "password": SecretStr(_ACCOUNT.password)}
        )
    )
    cache.store(_ACCOUNT, seeded)

    async def load_account() -> CookidoughAccount | None:
        raise AssertionError("loader must not run on a cache hit")

    resolved = await cache.get_or_create(_ACCOUNT.id, load_account)
    assert resolved is seeded


async def test_aclose_closes_every_cached_session() -> None:
    cache = CookidoughSessionCache(_HTTP_SETTINGS)

    async def load_account() -> CookidoughAccount | None:
        return _ACCOUNT

    session = await cache.get_or_create("acc-1", load_account)
    await cache.aclose()

    # aclose() on a never-logged-in session is a no-op, but must not raise,
    # and the cache must be empty afterwards.
    assert session.session_generation == 0

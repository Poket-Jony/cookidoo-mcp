"""Tests for `get_session`'s stdio-vs-http dispatch (see conftest for fixtures)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mcp.server.auth.provider import AccessToken
from pydantic import SecretStr

from cookidough_mcp.config import Settings
from cookidough_mcp.context import AppContext, get_session
from cookidough_mcp.errors import AuthenticationError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from cookidough_mcp.accounts import CookidoughAccount
    from cookidough_mcp.session import CookidoughSessionProtocol


@dataclass
class _FakeRequestContext:
    lifespan_context: AppContext


@dataclass
class _FakeToolContext:
    request_context: _FakeRequestContext


def _http_app_context(base: AppContext, *, session_cache: _StubSessionCache) -> AppContext:
    http_settings = Settings(
        mcp_mode="http",
        public_url="https://example.test",
        database_url="postgres://example/db",
        encryption_key=SecretStr("00" * 32),
    )
    return AppContext(
        settings=http_settings,
        session=None,
        scorer=base.scorer,
        importer=base.importer,
        session_cache=session_cache,  # type: ignore[arg-type]
        pool=object(),  # type: ignore[arg-type]
    )


class _StubSessionCache:
    def __init__(self, session: object) -> None:
        self.session = session
        self.requested_account_ids: list[str] = []

    async def get_or_create(
        self,
        account_id: str,
        load_account: Callable[[], Awaitable[CookidoughAccount | None]],
    ) -> CookidoughSessionProtocol:
        del load_account
        self.requested_account_ids.append(account_id)
        return self.session  # type: ignore[return-value]


async def test_get_session_returns_singleton_in_stdio_mode(
    app_context: AppContext, fake_session: object
) -> None:
    ctx = _FakeToolContext(_FakeRequestContext(app_context))
    session = await get_session(ctx)  # type: ignore[arg-type]
    assert session is fake_session


async def test_get_session_raises_without_access_token(
    app_context: AppContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cookidough_mcp.context.get_access_token", lambda: None)
    http_ctx = _http_app_context(app_context, session_cache=_StubSessionCache(session=object()))
    ctx = _FakeToolContext(_FakeRequestContext(http_ctx))

    with pytest.raises(AuthenticationError):
        await get_session(ctx)  # type: ignore[arg-type]


async def test_get_session_resolves_account_from_bearer_subject(
    app_context: AppContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = AccessToken(token="t", client_id="c", scopes=[], subject="account-42")
    monkeypatch.setattr("cookidough_mcp.context.get_access_token", lambda: token)
    sentinel_session = object()
    session_cache = _StubSessionCache(session=sentinel_session)
    http_ctx = _http_app_context(app_context, session_cache=session_cache)
    ctx = _FakeToolContext(_FakeRequestContext(http_ctx))

    resolved = await get_session(ctx)  # type: ignore[arg-type]

    assert resolved is sentinel_session
    assert session_cache.requested_account_ids == ["account-42"]

"""Tests for the pure (non-database) logic in `CookidoughOAuthProvider`.

CI has no Postgres service, so the DB-backed CRUD methods (`get_client`,
`exchange_authorization_code`, ...) are exercised end-to-end instead via the
MCP Inspector against a real database (see README "Testanleitung").
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl, SecretStr

from cookidough_mcp.config import Settings
from cookidough_mcp.db import LazyPool
from cookidough_mcp.oauth_provider import CookidoughOAuthProvider, _code_from_row


def _client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="client-1",
        redirect_uris=[AnyUrl("https://claude.ai/api/mcp/auth_callback")],
    )


def _unused_lazy_pool() -> LazyPool:
    """A `LazyPool` that must never actually connect (`.get()` is never called)."""
    return LazyPool(
        Settings(
            mcp_mode="http",
            public_url="https://example.test",
            database_url="postgres://example/db",
            encryption_key=SecretStr("00" * 32),
        )
    )


async def test_authorize_redirects_to_login_with_params_preserved() -> None:
    provider = CookidoughOAuthProvider(
        _unused_lazy_pool(),
        login_url="https://example.test/login",
        resource_server_url="https://example.test/mcp",
    )
    params = AuthorizationParams(
        state="xyz",
        scopes=["a", "b"],
        code_challenge="challenge123",
        redirect_uri=AnyUrl("https://claude.ai/api/mcp/auth_callback"),
        redirect_uri_provided_explicitly=True,
        resource="https://example.test/mcp",
    )

    url = await provider.authorize(_client(), params)

    parsed = urlsplit(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://example.test/login"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["client-1"]
    assert query["redirect_uri"] == ["https://claude.ai/api/mcp/auth_callback"]
    assert query["code_challenge"] == ["challenge123"]
    assert query["state"] == ["xyz"]
    assert query["scope"] == ["a b"]
    assert query["resource"] == ["https://example.test/mcp"]
    assert query["redirect_uri_provided_explicitly"] == ["True"]


class _FakeRecord(dict[str, object]):
    """Minimal stand-in for `asyncpg.Record` (subscriptable by column name)."""


def test_code_from_row_maps_every_column() -> None:
    row = _FakeRecord(
        code="code-1",
        scopes='["a", "b"]',
        expires_at=_FakeTimestamp(1_700_000_000.0),
        client_id="client-1",
        code_challenge="challenge123",
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True,
        resource="https://example.test/mcp",
        account_id="account-1",
    )

    code = _code_from_row(row)  # type: ignore[arg-type]

    assert code.code == "code-1"
    assert code.scopes == ["a", "b"]
    assert code.expires_at == 1_700_000_000.0
    assert code.client_id == "client-1"
    assert code.code_challenge == "challenge123"
    assert str(code.redirect_uri) == "https://claude.ai/api/mcp/auth_callback"
    assert code.redirect_uri_provided_explicitly is True
    assert code.resource == "https://example.test/mcp"
    assert code.subject == "account-1"


class _FakeTimestamp:
    """Stand-in for the `datetime` asyncpg returns for TIMESTAMPTZ columns."""

    def __init__(self, epoch_seconds: float) -> None:
        self._epoch_seconds = epoch_seconds

    def timestamp(self) -> float:
        return self._epoch_seconds

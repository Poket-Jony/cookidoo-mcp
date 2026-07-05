"""Lifespan-scoped application context shared with every tool invocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context

from .accounts import get_account_by_id
from .config import Settings, TransportMode
from .errors import AuthenticationError, UpstreamApiError
from .quality import QualityScorer
from .session import CookidoughSessionProtocol
from .web_import import WebRecipeImporter

if TYPE_CHECKING:
    import asyncpg

    from .accounts import CookidoughAccount
    from .session_cache import CookidoughSessionCache


@dataclass(frozen=True)
class AppContext:
    """Dependencies injected into every tool call via FastMCP's lifespan.

    ``session`` is the single global session used by the stdio transport
    (one Cookidoo account per process). The http transport is multi-tenant
    instead: ``session`` stays `None` and ``session_cache``/``pool`` resolve
    the right per-caller session on demand — see `get_session`.
    """

    settings: Settings
    session: CookidoughSessionProtocol | None
    scorer: QualityScorer
    importer: WebRecipeImporter
    session_cache: CookidoughSessionCache | None = None
    pool: asyncpg.Pool | None = None


ToolContext = Context[Any, AppContext, Any]


def get_context(ctx: ToolContext) -> AppContext:
    """Retrieve the injected `AppContext` from a tool's `Context`."""
    return ctx.request_context.lifespan_context


async def get_session(ctx: ToolContext) -> CookidoughSessionProtocol:
    """Resolve the `CookidoughSession` for the current tool call.

    stdio: returns the single process-wide session. http: resolves the
    authenticated caller (via the SDK's bearer-auth contextvar) to their own
    cached — or lazily logged-in — session, so concurrent callers never
    share a Cookidoo account.
    """
    app_context = get_context(ctx)
    if app_context.settings.mcp_mode is TransportMode.STDIO:
        if app_context.session is None:
            raise UpstreamApiError("Session is not initialized.")
        return app_context.session

    if app_context.session_cache is None or app_context.pool is None:
        raise UpstreamApiError("Session cache is not initialized for the http transport.")
    access_token = get_access_token()
    if access_token is None or access_token.subject is None:
        raise AuthenticationError("Request is not authenticated with a Cookidoo account.")

    account_id = access_token.subject
    pool = app_context.pool
    encryption_key = app_context.settings.encryption_key
    assert encryption_key is not None  # enforced by Settings.check_mode_requirements

    async def _load_account() -> CookidoughAccount | None:
        return await get_account_by_id(pool, account_id, encryption_key)

    return await app_context.session_cache.get_or_create(account_id, _load_account)

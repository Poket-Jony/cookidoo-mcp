"""FastMCP server assembly: lifespan, dependency injection and tool wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from . import db, oauth_web, resources
from .config import Settings, TransportMode
from .context import AppContext
from .oauth_provider import CookidoughOAuthProvider
from .quality import QualityScorer
from .session import CookidoughSession
from .session_cache import CookidoughSessionCache
from .tools import register_all
from .web_import import WebRecipeImporter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def build_server(settings: Settings | None = None) -> FastMCP:
    """Construct the FastMCP server with all tools registered."""
    resolved = settings if settings is not None else Settings.from_env()

    if resolved.mcp_mode is TransportMode.STDIO:
        return _build_stdio_server(resolved)
    return _build_http_server(resolved)


def _build_stdio_server(resolved: Settings) -> FastMCP:
    """Single-tenant server for Claude Desktop: one Cookidoo account, one process."""

    @asynccontextmanager
    async def lifespan(_mcp: FastMCP) -> AsyncIterator[AppContext]:
        session = CookidoughSession(resolved)
        try:
            yield AppContext(
                settings=resolved,
                session=session,
                scorer=QualityScorer(threshold=resolved.quality_bar),
                importer=WebRecipeImporter(),
            )
        finally:
            await session.aclose()

    mcp = FastMCP(
        name="cookidough",
        lifespan=lifespan,
        host=resolved.mcp_host,
        port=resolved.mcp_port,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    register_all(mcp)
    resources.register(mcp)
    return mcp


def _build_http_server(resolved: Settings) -> FastMCP:
    """Multi-tenant server: each caller authenticates via our own OAuth login page."""
    assert resolved.public_url is not None  # enforced by Settings.check_mode_requirements

    provider = CookidoughOAuthProvider(
        login_url=resolved.login_url,
        resource_server_url=resolved.resource_server_url,
    )
    session_cache = CookidoughSessionCache(resolved)

    @asynccontextmanager
    async def lifespan(_mcp: FastMCP) -> AsyncIterator[AppContext]:
        pool = await db.create_pool(resolved)
        provider.set_pool(pool)
        await db.run_migrations(pool)
        cleanup_task = db.start_cleanup_task(pool)
        try:
            yield AppContext(
                settings=resolved,
                session=None,
                scorer=QualityScorer(threshold=resolved.quality_bar),
                importer=WebRecipeImporter(),
                session_cache=session_cache,
                pool=pool,
            )
        finally:
            await db.stop_cleanup_task(cleanup_task)
            await session_cache.aclose()
            await pool.close()

    mcp = FastMCP(
        name="cookidough",
        lifespan=lifespan,
        host=resolved.mcp_host,
        port=resolved.mcp_port,
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(resolved.public_url),
            resource_server_url=AnyHttpUrl(resolved.resource_server_url),
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        ),
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    register_all(mcp)
    resources.register(mcp)
    oauth_web.register(mcp, provider=provider, settings=resolved, session_cache=session_cache)
    return mcp

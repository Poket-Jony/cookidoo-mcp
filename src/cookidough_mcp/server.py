"""FastMCP server assembly: lifespan, dependency injection and tool wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import resources
from .config import Settings
from .context import AppContext
from .quality import QualityScorer
from .session import CookidoughSession
from .tools import register_all
from .web_import import WebRecipeImporter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def build_server(settings: Settings | None = None) -> FastMCP:
    """Construct the FastMCP server with all tools registered."""
    resolved = settings if settings is not None else Settings.from_env()

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
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )
    register_all(mcp)
    resources.register(mcp)
    return mcp

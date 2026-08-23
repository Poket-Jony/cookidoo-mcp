"""MCP server assembly: lifespan, dependency injection and tool wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer

from . import resources
from .config import Settings
from .context import AppContext
from .quality import QualityScorer
from .session import CookidoughSession
from .tools import register_all
from .web_import import WebRecipeImporter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def build_server(settings: Settings | None = None) -> MCPServer:
    """Construct the MCP server with all tools registered."""
    resolved = settings if settings is not None else Settings.from_env()

    # Built outside the lifespan so static resources can close over it: mcp 2.0
    # rejects a ``Context`` parameter on a non-template resource URI.
    app = AppContext(
        settings=resolved,
        session=CookidoughSession(resolved),
        scorer=QualityScorer(threshold=resolved.quality_bar),
        importer=WebRecipeImporter(),
    )

    @asynccontextmanager
    async def lifespan(_mcp: MCPServer) -> AsyncIterator[AppContext]:
        try:
            yield app
        finally:
            await app.session.aclose()

    mcp = MCPServer(name="cookidough", lifespan=lifespan)
    register_all(mcp)
    resources.register(mcp, app)
    return mcp

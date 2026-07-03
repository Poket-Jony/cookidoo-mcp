"""FastMCP server assembly: lifespan, dependency injection and tool wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from . import resources
from .config import Settings
from .context import AppContext
from .quality import QualityScorer
from .session import CookidoughSession
from .tools import register_all
from .web_import import WebRecipeImporter
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "cookidough",
    ...,  # bestehende Parameter unverändert lassen
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

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

    mcp = FastMCP(name="cookidough", lifespan=lifespan)
    register_all(mcp)
    resources.register(mcp)
    return mcp

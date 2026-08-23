"""Lifespan-scoped application context shared with every tool invocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import Context

from .config import Settings
from .quality import QualityScorer
from .session import CookidoughSessionProtocol
from .web_import import WebRecipeImporter


@dataclass(frozen=True)
class AppContext:
    """Dependencies injected into every tool call via the MCP server's lifespan."""

    settings: Settings
    session: CookidoughSessionProtocol
    scorer: QualityScorer
    importer: WebRecipeImporter


ToolContext = Context[AppContext, Any]


def get_context(ctx: ToolContext) -> AppContext:
    """Retrieve the injected `AppContext` from a tool's `Context`."""
    return ctx.request_context.lifespan_context

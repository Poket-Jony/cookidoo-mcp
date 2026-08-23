"""Tool registration entrypoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import auth, calendar, collections, discovery, interactions, recipes, shopping

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


def register_all(mcp: MCPServer) -> None:
    """Register all tool modules onto the given MCPServer instance."""
    for module in (auth, recipes, collections, shopping, calendar, discovery, interactions):
        module.register(mcp)


__all__ = ["register_all"]

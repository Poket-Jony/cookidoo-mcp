"""Managed and custom collection tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..context import ToolContext, get_session
from ..models import CollectionPage, CollectionSummary

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_managed_collections(ctx: ToolContext, page: int = 0) -> CollectionPage:
        """List the user's managed Cookidoo collections (Cookbooks).

        Returns one page of ``items`` plus ``total_pages``/``total_elements``
        so callers know whether to request further pages.
        """
        return await (await get_session(ctx)).list_managed_collections(page=page)

    @mcp.tool()
    async def add_managed_collection(ctx: ToolContext, collection_id: str) -> CollectionSummary:
        """Subscribe to an existing managed Cookidoo collection by its ID."""
        return await (await get_session(ctx)).add_managed_collection(collection_id)

    @mcp.tool()
    async def remove_managed_collection(ctx: ToolContext, collection_id: str) -> str:
        """Unsubscribe from a managed collection by its ID."""
        await (await get_session(ctx)).remove_managed_collection(collection_id)
        return f"Removed managed collection {collection_id}."

    @mcp.tool()
    async def list_custom_collections(ctx: ToolContext, page: int = 0) -> CollectionPage:
        """List the user's own custom collections.

        Returns one page of ``items`` plus ``total_pages``/``total_elements``
        so callers know whether to request further pages.
        """
        return await (await get_session(ctx)).list_custom_collections(page=page)

    @mcp.tool()
    async def create_custom_collection(ctx: ToolContext, name: str) -> CollectionSummary:
        """Create a new empty custom collection with the given name."""
        return await (await get_session(ctx)).create_custom_collection(name)

    @mcp.tool()
    async def delete_custom_collection(ctx: ToolContext, collection_id: str) -> str:
        """Delete a custom collection (the recipes themselves are kept)."""
        await (await get_session(ctx)).delete_custom_collection(collection_id)
        return f"Deleted custom collection {collection_id}."

    @mcp.tool()
    async def add_recipes_to_custom_collection(
        ctx: ToolContext, collection_id: str, recipe_ids: list[str]
    ) -> CollectionSummary:
        """Add one or more recipes to a custom collection."""
        return await (await get_session(ctx)).add_recipes_to_custom_collection(
            collection_id, recipe_ids
        )

    @mcp.tool()
    async def remove_recipe_from_custom_collection(
        ctx: ToolContext, collection_id: str, recipe_id: str
    ) -> str:
        """Remove a single recipe from a custom collection."""
        await (await get_session(ctx)).remove_recipe_from_custom_collection(
            collection_id, recipe_id
        )
        return f"Removed recipe {recipe_id} from collection {collection_id}."

"""Meal plan / calendar tools."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from ..context import ToolContext, get_session
from ..models import CalendarDay

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_calendar_week(ctx: ToolContext, day: date) -> list[CalendarDay]:
        """Return the meal plan for the calendar week containing the given date."""
        return await (await get_session(ctx)).get_calendar_week(day)

    @mcp.tool()
    async def add_recipes_to_calendar(
        ctx: ToolContext, day: date, recipe_ids: list[str]
    ) -> CalendarDay:
        """Schedule one or more recipes for a specific date in the meal plan."""
        return await (await get_session(ctx)).add_recipes_to_calendar(day, recipe_ids)

    @mcp.tool()
    async def remove_recipe_from_calendar(
        ctx: ToolContext, day: date, recipe_id: str
    ) -> CalendarDay:
        """Remove a single planned recipe from the given date."""
        return await (await get_session(ctx)).remove_recipe_from_calendar(day, recipe_id)

    @mcp.tool()
    async def add_custom_recipes_to_calendar(
        ctx: ToolContext, day: date, recipe_ids: list[str]
    ) -> CalendarDay:
        """Schedule one or more **custom** recipes for the given date.

        Use ``add_recipes_to_calendar`` for regular Cookidoo recipes; this
        endpoint targets the user's own custom recipes (those listed by
        ``list_custom_recipes``).
        """
        return await (await get_session(ctx)).add_custom_recipes_to_calendar(day, recipe_ids)

    @mcp.tool()
    async def remove_custom_recipe_from_calendar(
        ctx: ToolContext, day: date, recipe_id: str
    ) -> CalendarDay:
        """Remove a single planned **custom** recipe from the given date."""
        return await (await get_session(ctx)).remove_custom_recipe_from_calendar(day, recipe_id)

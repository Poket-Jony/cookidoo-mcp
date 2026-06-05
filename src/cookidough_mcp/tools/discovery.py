"""Discovery tools: full-text recipe search and ingredient-based suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..context import ToolContext, get_context
from ..models import RecipeSearchResult, RecipeSuggestion

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search_recipes(
        ctx: ToolContext,
        query: str,
        limit: int = 10,
        max_total_minutes: int | None = None,
        difficulty: str | None = None,
        categories: list[str] | None = None,
        ingredients: list[str] | None = None,
        exclude_ingredients: list[str] | None = None,
        min_rating: float | None = None,
        portions: int | None = None,
        thermomix_version: str | None = None,
        accessories: list[str] | None = None,
        sort_by: str | None = None,
    ) -> list[RecipeSearchResult]:
        """Search the Cookidoo recipe library by keyword, optionally filtered.

        Returns up to ``limit`` (default 10, max 50) matching recipes sorted
        by Cookidoo's own relevance ranking. The query is matched against the
        configured locale (`COOKIDOUGH_COUNTRY` / `COOKIDOUGH_LANGUAGE`).

        All filters are optional and follow the Cookidoo web search:
        ``max_total_minutes`` caps the total time; ``difficulty`` is
        ``easy``/``medium``/``advanced``; ``ingredients`` /
        ``exclude_ingredients`` require/forbid ingredient names;
        ``min_rating`` keeps recipes rated at least that many stars (1-5);
        ``thermomix_version`` is ``TM5``/``TM6``/``TM7``; ``sort_by``
        accepts Cookidoo sort keys (e.g. ``relevance``, ``rating``).
        """
        return await get_context(ctx).session.search_recipes(
            query,
            limit,
            max_total_minutes=max_total_minutes,
            difficulty=difficulty,
            categories=categories,
            ingredients=ingredients,
            exclude_ingredients=exclude_ingredients,
            min_rating=min_rating,
            portions=portions,
            thermomix_version=thermomix_version,
            accessories=accessories,
            sort_by=sort_by,
        )

    @mcp.tool()
    async def suggest_recipes_from_ingredients(
        ctx: ToolContext,
        available_ingredients: list[str],
        collection_ids: list[str] | None = None,
        max_results: int = 10,
    ) -> list[RecipeSuggestion]:
        """Suggest recipes by ingredient match, ranked by match score.

        Without ``collection_ids`` the whole Cookidoo library is searched
        (server-side ingredient filter, then locally re-ranked). With
        ``collection_ids`` only the recipes inside those collections are
        considered. Each result carries the match score (0.0-1.0), the
        matching and missing ingredient names, and the full
        ``RecipeDetails`` payload.

        Tip: keep ``available_ingredients`` short and use head nouns
        (``"chicken"``, ``"rice"``) — substring matching means "rice"
        matches "basmati rice", "wild rice", etc.
        """
        return await get_context(ctx).session.suggest_recipes_from_ingredients(
            available_ingredients=available_ingredients,
            collection_ids=collection_ids,
            max_results=max_results,
        )

    @mcp.tool()
    async def get_recipe_recommendations(
        ctx: ToolContext, recipe_id: str | None = None, limit: int = 10
    ) -> list[RecipeSearchResult]:
        """Get personalized recipe recommendations from Cookidoo.

        Without ``recipe_id`` this returns the user's "For you" feed.
        With ``recipe_id`` it returns recipes similar to that one.
        An empty list means Cookidoo had no recommendations available.
        """
        return await get_context(ctx).session.get_recipe_recommendations(recipe_id, limit)

"""Recipe interaction tools: rating, bookmark, personal note, cooked-history.

These wrap Cookidoo endpoints that are not part of ``cookidoo-api``; the
session layer talks to them directly over the authenticated HTTP channel.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..context import ToolContext, get_session
from ..errors import NotFoundError, UpstreamApiError
from ..models import CookedRecipe, RecipeInteractionResult, RecipeSearchResult
from ..session import CookidoughSessionProtocol

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any

    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def set_recipe_interactions(
        ctx: ToolContext,
        recipe_id: str,
        rating: int | None = None,
        bookmarked: bool | None = None,
        note: str | None = None,
        mark_cooked: bool = False,
        is_custom_recipe: bool = False,
    ) -> RecipeInteractionResult:
        """Set the user's interactions with a recipe in one call.

        Provide at least one action: ``rating`` (1-5 stars), ``bookmarked``
        (true saves, false removes the bookmark), ``note`` (personal note
        text; an empty string deletes the note), ``mark_cooked`` (true logs
        the recipe in the cooking history). Set ``is_custom_recipe=true``
        when logging one of your own recipes as cooked; rating, bookmark
        and note apply to catalogue recipes only.

        Actions run independently — the result reports ``"ok"`` or
        ``"failed: …"`` per action instead of failing the whole call.
        Read everything back via ``get_recipe_details`` with
        ``include_interactions=true``.
        """
        if rating is None and bookmarked is None and note is None and not mark_cooked:
            raise ValueError(
                "Provide at least one action: rating, bookmarked, note or mark_cooked."
            )
        session = await get_session(ctx)
        actions = _build_actions(
            session,
            recipe_id,
            rating=rating,
            bookmarked=bookmarked,
            note=note,
            mark_cooked=mark_cooked,
            is_custom_recipe=is_custom_recipe,
        )
        outcomes = dict(
            await asyncio.gather(*(_run_action(field, coro) for field, coro in actions))
        )
        return RecipeInteractionResult(recipe_id=recipe_id, **outcomes)

    @mcp.tool()
    async def list_bookmarked_recipes(ctx: ToolContext) -> list[RecipeSearchResult]:
        """List the recipes the user has bookmarked ("My recipes")."""
        return await (await get_session(ctx)).list_bookmarked_recipes()

    @mcp.tool()
    async def get_cooking_history(ctx: ToolContext, limit: int = 20) -> list[CookedRecipe]:
        """List the recipes the user has logged as cooked, newest first."""
        return await (await get_session(ctx)).get_cooking_history(limit)


def _build_actions(
    session: CookidoughSessionProtocol,
    recipe_id: str,
    *,
    rating: int | None,
    bookmarked: bool | None,
    note: str | None,
    mark_cooked: bool,
    is_custom_recipe: bool,
) -> list[tuple[str, Coroutine[Any, Any, None]]]:
    actions: list[tuple[str, Coroutine[Any, Any, None]]] = []
    if rating is not None:
        actions.append(("rating", session.rate_recipe(recipe_id, rating)))
    if bookmarked is not None:
        actions.append(("bookmark", session.set_recipe_bookmark(recipe_id, bookmarked)))
    if note is not None:
        actions.append(("note", session.set_recipe_note(recipe_id, note)))
    if mark_cooked:
        actions.append(("cooked", session.mark_recipe_cooked(recipe_id, is_custom_recipe)))
    return actions


async def _run_action(field: str, coro: Coroutine[Any, Any, None]) -> tuple[str, str]:
    # AuthenticationError propagates — if the session is broken, every
    # action fails the same way and a per-field report would only obscure it.
    try:
        await coro
    except (NotFoundError, UpstreamApiError) as e:
        return field, f"failed: {e}"
    return field, "ok"

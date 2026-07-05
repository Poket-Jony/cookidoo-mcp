"""Per-account `CookidoughSession` cache for the http (multi-tenant) transport.

One live session per Cookidoo account, reused across every tool call and every
OAuth client (Claude.ai, MCP Inspector, ...) that authenticated as that
account — mirrors `CookidoughSession`'s own re-login-on-401 behaviour, just
scoped per account instead of per process.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import SecretStr

from .errors import AuthenticationError
from .session import CookidoughSession

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .accounts import CookidoughAccount
    from .config import Settings


class CookidoughSessionCache:
    """Lazily builds and caches one `CookidoughSession` per account id."""

    def __init__(self, base_settings: Settings) -> None:
        self._base_settings = base_settings
        self._sessions: dict[str, CookidoughSession] = {}
        self._lock = asyncio.Lock()

    def store(self, account: CookidoughAccount, session: CookidoughSession) -> None:
        """Seed the cache with an already-logged-in session (post-login-page success)."""
        self._sessions[account.id] = session

    async def get_or_create(
        self,
        account_id: str,
        load_account: Callable[[], Awaitable[CookidoughAccount | None]],
    ) -> CookidoughSession:
        async with self._lock:
            session = self._sessions.get(account_id)
            if session is not None:
                return session
            account = await load_account()
            if account is None:
                raise AuthenticationError(f"Unknown Cookidoo account id {account_id!r}.")
            session = self._build_session(account)
            self._sessions[account_id] = session
            return session

    def _build_session(self, account: CookidoughAccount) -> CookidoughSession:
        per_account_settings = self._base_settings.model_copy(
            update={"email": account.email, "password": SecretStr(account.password)}
        )
        return CookidoughSession(per_account_settings)

    async def aclose(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        for session in sessions:
            await session.aclose()

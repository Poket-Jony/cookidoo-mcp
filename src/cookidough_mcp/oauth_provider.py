"""OAuth 2.1 authorization server provider backing the http transport.

Cookidoo itself is not an OAuth provider (email/password against its own
CIAM), so this server acts as its own Authorization Server: clients (Claude.ai
et al.) go through the standard `/authorize` → `/token` dance against *us*,
while the actual credential check happens on our own login page
(`oauth_web.py`) against the live Cookidoo API.

Access/refresh tokens are stored as SHA-256 hashes (never the raw value), and
every authorization code / token is bound to the account that logged in via
`subject`/`account_id`, so `context.get_session` can resolve the right
per-caller `CookidoughSession`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from .crypto import new_id, random_token, sha256_hex

if TYPE_CHECKING:
    import asyncpg
    from asyncpg import Record

_CODE_TTL_SECONDS = 60
_ACCESS_TOKEN_TTL_SECONDS = 60 * 60
_REFRESH_TOKEN_TTL_SECONDS = 90 * 24 * 60 * 60


def _code_from_row(row: Record) -> AuthorizationCode:
    return AuthorizationCode(
        code=row["code"],
        scopes=json.loads(row["scopes"]),
        expires_at=row["expires_at"].timestamp(),
        client_id=row["client_id"],
        code_challenge=row["code_challenge"],
        redirect_uri=AnyUrl(row["redirect_uri"]),
        redirect_uri_provided_explicitly=row["redirect_uri_provided_explicitly"],
        resource=row["resource"],
        subject=row["account_id"],
    )


class CookidoughOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """Postgres-backed `OAuthAuthorizationServerProvider` for the http transport.

    The pool is created inside FastMCP's async lifespan (it must share that
    event loop), but this provider has to exist already when `FastMCP(...)`
    is constructed. `set_pool` bridges the two: the lifespan calls it once
    the pool is ready, before the ASGI app starts accepting requests.
    """

    def __init__(self, *, login_url: str, resource_server_url: str) -> None:
        self._pool: asyncpg.Pool | None = None
        self._login_url = login_url
        self._resource_server_url = resource_server_url

    def set_pool(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "set_pool() must run before the provider is used."
        return self._pool

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = await self.pool.fetchrow(
            "SELECT data FROM oauth_clients WHERE client_id = $1", client_id
        )
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(json.loads(row["data"]))

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        assert client_info.client_id is not None
        await self.pool.execute(
            "INSERT INTO oauth_clients (client_id, data) VALUES ($1, $2::jsonb)",
            client_info.client_id,
            client_info.model_dump_json(),
        )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Redirect to our own login page; it carries every param as a query string.

        The login page's form later posts back to `/login/callback` (see
        `oauth_web.py`) with these as hidden fields plus the entered Cookidoo
        credentials — `authorize()` itself never sees a request body, so
        nothing can be persisted here beyond what fits in this redirect URL.
        """
        query = urlencode(
            {
                "client_id": client.client_id or "",
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": str(params.redirect_uri_provided_explicitly),
                "code_challenge": params.code_challenge,
                "state": params.state or "",
                "scope": " ".join(params.scopes or []),
                "resource": params.resource or "",
            }
        )
        return f"{self._login_url}?{query}"

    async def create_authorization_code(
        self,
        *,
        client_id: str,
        account_id: str,
        redirect_uri: AnyUrl,
        redirect_uri_provided_explicitly: bool,
        code_challenge: str,
        scopes: list[str],
        resource: str | None,
    ) -> str:
        """Issue a fresh authorization code after a successful Cookidoo login.

        Called by the `/login/callback` route, not part of the SDK's
        provider protocol.
        """
        code = random_token()
        await self.pool.execute(
            """
            INSERT INTO oauth_codes
                (code, client_id, account_id, redirect_uri, redirect_uri_provided_explicitly,
                 code_challenge, scopes, resource, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, now() + make_interval(secs => $9))
            """,
            code,
            client_id,
            account_id,
            str(redirect_uri),
            redirect_uri_provided_explicitly,
            code_challenge,
            json.dumps(scopes),
            resource,
            _CODE_TTL_SECONDS,
        )
        return code

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        row = await self.pool.fetchrow(
            """
            SELECT * FROM oauth_codes
            WHERE code = $1 AND client_id = $2 AND used_at IS NULL AND expires_at > now()
            """,
            authorization_code,
            client.client_id,
        )
        return None if row is None else _code_from_row(row)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        row = await self.pool.fetchrow(
            """
            UPDATE oauth_codes SET used_at = now()
            WHERE code = $1 AND used_at IS NULL AND expires_at > now()
            RETURNING account_id, scopes, resource
            """,
            authorization_code.code,
        )
        if row is None:
            raise TokenError(
                error="invalid_grant",
                error_description="Authorization code was already used or has expired.",
            )
        return await self._issue_tokens(
            client_id=authorization_code.client_id,
            account_id=row["account_id"],
            scopes=json.loads(row["scopes"]),
            resource=row["resource"],
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = await self.pool.fetchrow(
            """
            SELECT * FROM oauth_tokens
            WHERE refresh_token_hash = $1 AND client_id = $2
              AND revoked_at IS NULL AND refresh_token_expires_at > now()
            """,
            sha256_hex(refresh_token),
            client.client_id,
        )
        if row is None:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=json.loads(row["scopes"]),
            expires_at=int(row["refresh_token_expires_at"].timestamp()),
            subject=row["account_id"],
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotation: the old refresh token is revoked in the same statement that
        # confirms it was still valid, so a replayed refresh token can only
        # ever win this race once.
        row = await self.pool.fetchrow(
            """
            UPDATE oauth_tokens SET revoked_at = now()
            WHERE refresh_token_hash = $1 AND revoked_at IS NULL
            RETURNING account_id, resource
            """,
            sha256_hex(refresh_token.token),
        )
        if row is None:
            raise TokenError(
                error="invalid_grant",
                error_description="Refresh token was already used or revoked.",
            )
        return await self._issue_tokens(
            client_id=client.client_id or refresh_token.client_id,
            account_id=row["account_id"],
            scopes=scopes,
            resource=row["resource"],
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = await self.pool.fetchrow(
            """
            SELECT * FROM oauth_tokens
            WHERE access_token_hash = $1 AND revoked_at IS NULL AND access_token_expires_at > now()
            """,
            sha256_hex(token),
        )
        if row is None:
            return None
        # RFC 8707 audience check: a token issued for a different resource
        # server must never authenticate a request here.
        if row["resource"] is not None and row["resource"] != self._resource_server_url:
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=json.loads(row["scopes"]),
            expires_at=int(row["access_token_expires_at"].timestamp()),
            resource=row["resource"],
            subject=row["account_id"],
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        token_hash = sha256_hex(token.token)
        await self.pool.execute(
            "UPDATE oauth_tokens SET revoked_at = now() "
            "WHERE (access_token_hash = $1 OR refresh_token_hash = $1) AND revoked_at IS NULL",
            token_hash,
        )

    async def _issue_tokens(
        self, *, client_id: str, account_id: str, scopes: list[str], resource: str | None
    ) -> OAuthToken:
        access_token = random_token()
        refresh_token = random_token()
        await self.pool.execute(
            """
            INSERT INTO oauth_tokens
                (id, access_token_hash, refresh_token_hash, client_id, account_id,
                 scopes, resource, access_token_expires_at, refresh_token_expires_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7,
                    now() + make_interval(secs => $8), now() + make_interval(secs => $9))
            """,
            new_id(),
            sha256_hex(access_token),
            sha256_hex(refresh_token),
            client_id,
            account_id,
            json.dumps(scopes),
            resource,
            _ACCESS_TOKEN_TTL_SECONDS,
            _REFRESH_TOKEN_TTL_SECONDS,
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(scopes) or None,
            refresh_token=refresh_token,
        )


__all__ = ["CookidoughOAuthProvider"]

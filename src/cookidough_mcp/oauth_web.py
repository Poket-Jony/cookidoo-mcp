"""Public (unauthenticated) HTTP routes that complete the OAuth login flow.

`CookidoughOAuthProvider.authorize()` can only return a redirect URL — it has
no access to a request body — so the actual Cookidoo credential form lives
here instead, as two `@mcp.custom_route` endpoints mounted alongside the MCP
endpoint:

* ``GET /login``: renders the form, carrying every `/authorize` parameter
  forward as hidden fields (see `oauth_provider.authorize`).
* ``POST /login/callback``: re-validates `client_id`/`redirect_uri` against
  the registered client (this route is *not* covered by the SDK's own
  `/authorize` guard), checks the credentials live against Cookidoo, and on
  success issues an authorization code and redirects back to the client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.auth.provider import construct_redirect_uri
from mcp.shared.auth import InvalidRedirectUriError
from pydantic import AnyUrl, SecretStr
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from .accounts import upsert_account
from .errors import AuthenticationError, UpstreamApiError
from .login_page import render_login_page
from .session import CookidoughSession

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from .config import Settings
    from .db import LazyPool
    from .oauth_provider import CookidoughOAuthProvider
    from .session_cache import CookidoughSessionCache


def _form_field(form: dict[str, str], name: str) -> str:
    value = form.get(name, "")
    return value if isinstance(value, str) else ""


def register(
    mcp: FastMCP,
    *,
    provider: CookidoughOAuthProvider,
    settings: Settings,
    session_cache: CookidoughSessionCache,
    lazy_pool: LazyPool,
) -> None:
    assert settings.encryption_key is not None  # enforced by Settings.check_mode_requirements

    @mcp.custom_route("/login", methods=["GET"])
    async def login_page(request: Request) -> Response:
        params = {name: request.query_params.get(name, "") for name in _PARAM_NAMES}
        return HTMLResponse(render_login_page(params=params, error_message=None))

    @mcp.custom_route("/login/callback", methods=["POST"])
    async def login_callback(request: Request) -> Response:
        form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
        params = {name: _form_field(form, name) for name in _PARAM_NAMES}

        client_id = params["client_id"]
        code_challenge = params["code_challenge"]
        redirect_uri_raw = params["redirect_uri"]
        state = params["state"] or None
        resource = params["resource"] or None
        scopes = params["scope"].split(" ") if params["scope"] else []
        email = _form_field(form, "email")
        password = _form_field(form, "password")

        if not client_id or not redirect_uri_raw or not code_challenge or not email or not password:
            return PlainTextResponse("Missing required fields.", status_code=400)

        client = await provider.get_client(client_id)
        if client is None:
            return PlainTextResponse("Unknown client.", status_code=400)

        try:
            redirect_uri = client.validate_redirect_uri(AnyUrl(redirect_uri_raw))
        except InvalidRedirectUriError:
            return PlainTextResponse("Invalid redirect_uri.", status_code=400)

        if resource is not None and resource != settings.resource_server_url:
            return HTMLResponse(
                render_login_page(params=params, error_message="Ungültige Resource-Anfrage."),
                status_code=400,
            )

        session = CookidoughSession(
            settings.model_copy(update={"email": email, "password": SecretStr(password)})
        )
        try:
            await session.__aenter__()
        except (AuthenticationError, UpstreamApiError):
            return HTMLResponse(
                render_login_page(
                    params=params, error_message="Cookidoo-E-Mail oder Passwort falsch."
                )
            )

        assert settings.encryption_key is not None  # enforced by Settings.check_mode_requirements
        account = await upsert_account(lazy_pool, email, password, settings.encryption_key)
        session_cache.store(account, session)

        code = await provider.create_authorization_code(
            client_id=client_id,
            account_id=account.id,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=params["redirect_uri_provided_explicitly"] == "True",
            code_challenge=code_challenge,
            scopes=scopes,
            resource=resource,
        )
        return RedirectResponse(
            url=construct_redirect_uri(str(redirect_uri), code=code, state=state),
            status_code=302,
        )


_PARAM_NAMES = (
    "client_id",
    "redirect_uri",
    "redirect_uri_provided_explicitly",
    "code_challenge",
    "state",
    "scope",
    "resource",
)

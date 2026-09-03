"""Cookidoo China login adapter.

The mainland deployment uses a phone-number form and different CIAM hosts from
the global Cookidoo API. This adapter authenticates through the official web
flow while retaining the session-cookie interface used by the MCP facade.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from http import HTTPStatus
from typing import Any, cast
from urllib.parse import urljoin

from aiohttp import ClientSession
from cookidoo_api import Cookidoo, CookidooConfig, CookidooLocalizationConfig
from cookidoo_api.exceptions import CookidooRequestException
from qcloud_cos import CosConfig, CosS3Client

from .errors import AuthenticationError

_LOGIN_FORM_ACTION_RE = re.compile(r'<form[^>]+action=["\']([^"\']*loginbyphone[^"\']*)', re.I)
_LOGIN_STATE_RE = re.compile(
    r'(?:<input[^>]+name=["\']login_auth_state["\'][^>]+value=["\']|'
    r'login_auth_state\s*=\s*["\'])([^"\']+)',
    re.I,
)
_BOOTSTRAP_ACTION_RE = re.compile(
    r'form\.action\s*=\s*["\']([^"\']*/oidc/auth/[^"\']+/login)["\']', re.I
)


class ChinaCookidoo(Cookidoo):
    """Cookidoo client for the official mainland-China phone/password login."""

    def __init__(self, session: ClientSession, *, phone_number: str, password: str) -> None:
        super().__init__(
            session=session,
            cfg=CookidooConfig(
                email=phone_number,
                password=password,
                localization=CookidooLocalizationConfig(
                    country_code="cn",
                    language="zh-Hans-CN",
                    url="https://cookidoo.com.cn/foundation/zh-Hans-CN",
                ),
            ),
        )

    @staticmethod
    def extract_login_form(login_html: str, page_url: str) -> tuple[str, str]:
        """Get the password-login POST target and one-time state from CIAM HTML."""
        action_match = _LOGIN_FORM_ACTION_RE.search(login_html)
        if action_match is None:
            raise AuthenticationError("China login page did not expose its phone-password form.")
        state_match = _LOGIN_STATE_RE.search(login_html)
        if state_match is None:
            raise AuthenticationError("China login page did not expose login_auth_state.")
        return urljoin(page_url, action_match.group(1)), state_match.group(1)

    @staticmethod
    def normalize_custom_recipe(payload: dict[str, Any]) -> dict[str, Any]:
        """Map the China API's field names into the global client shape."""
        normalized = dict(payload)
        content = dict(payload.get("recipeContent") or {})
        content["ingredients"] = list(content.get("recipeIngredient") or [])
        content["instructions"] = list(content.get("recipeInstructions") or [])
        content["tools"] = list(content.get("tool") or [])
        content.setdefault("totalTime", "PT0S")
        content.setdefault("prepTime", "PT0S")
        normalized["recipeContent"] = content
        return normalized

    @staticmethod
    def update_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Translate a generic draft into the China editor's PATCH body."""
        ingredients = payload.get("ingredients") or []
        instructions = payload.get("instructions") or []
        return {
            "name": payload["name"],
            "tools": list(payload.get("tools") or []),
            "yield": payload.get("yield") or {},
            "ingredients": ingredients,
            "instructions": instructions,
            "recipeMetadata": payload.get("recipeMetadata") or {},
        }

    @classmethod
    async def resolve_password_login_form(
        cls, session: ClientSession, login_html: str, page_url: str
    ) -> tuple[str, str]:
        """Follow the CIAM JavaScript bootstrap page to the password form."""
        if _LOGIN_FORM_ACTION_RE.search(login_html):
            return cls.extract_login_form(login_html, page_url)
        bootstrap_match = _BOOTSTRAP_ACTION_RE.search(login_html)
        state_match = _LOGIN_STATE_RE.search(login_html)
        if bootstrap_match is None or state_match is None:
            raise AuthenticationError("China login page did not expose its password-login route.")
        async with session.post(
            urljoin(page_url, bootstrap_match.group(1)),
            data={"login_auth_state": state_match.group(1)},
            allow_redirects=True,
        ) as response:
            if response.status != HTTPStatus.OK:
                raise AuthenticationError(f"China login form returned HTTP {response.status}.")
            return cls.extract_login_form(await response.text(), str(response.url))

    async def get_custom_recipe(self, id: str) -> Any:
        """Fetch and normalize the mainland API's custom recipe payload."""
        path = f"created-recipes/{self.localization.language}/{id}"
        async with self._session.get(
            self.api_endpoint / path, headers=self._api_headers
        ) as response:
            if response.status == HTTPStatus.UNAUTHORIZED:
                raise AuthenticationError("China Cookidoo session is no longer authorized.")
            response.raise_for_status()
            payload = self.normalize_custom_recipe(await response.json())
        from cookidoo_api.helpers import cookidoo_custom_recipe_from_json

        return cookidoo_custom_recipe_from_json(cast(Any, payload), self.localization)

    async def upload_custom_recipe_image(self, image_bytes: bytes, content_type: str) -> str:
        """Upload an image with China COS credentials and wait for moderation."""
        image_format = "png" if content_type == "image/png" else "jpg"
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "xmlhttprequest",
            "correlation-id": str(uuid.uuid4()),
        }
        allocation_url = self.api_endpoint / (
            f"content-moderation/customer_recipe/upload/objectId?format={image_format}"
        )
        async with self._session.get(allocation_url, headers=headers) as response:
            response.raise_for_status()
            allocation = await response.json()
        object_id = allocation.get("objectId")
        token_url = (
            self.api_endpoint / f"content-moderation/customer_recipe/upload/{object_id}/token"
        )
        async with self._session.get(token_url, headers=headers) as response:
            response.raise_for_status()
            token_map = (await response.json()).get("tokenMap")
        param_map = allocation.get("paramMap")
        folder = allocation.get("folder")
        if not isinstance(object_id, str) or not isinstance(token_map, dict):
            raise CookidooRequestException("China image upload did not return usable credentials.")
        if not isinstance(param_map, dict) or not isinstance(folder, str):
            raise CookidooRequestException("China image upload did not return a target location.")
        try:
            cos = CosS3Client(
                CosConfig(
                    Region=param_map["region"],
                    SecretId=token_map["tmpSecretId"],
                    SecretKey=token_map["tmpSecretKey"],
                    Token=token_map["sessionToken"],
                    Scheme="https",
                    Timeout=120,
                )
            )
            await asyncio.to_thread(
                cos.put_object,
                Bucket=param_map["bucket"],
                Key=folder + object_id,
                Body=image_bytes,
                ContentType=content_type,
            )
        except (KeyError, TypeError) as exc:
            raise CookidooRequestException("China image upload credentials were invalid.") from exc

        audit_url = self.api_endpoint / f"content-moderation/customer_recipe/audit/img/{object_id}"
        for _ in range(30):
            await asyncio.sleep(2)
            async with self._session.get(audit_url, headers=headers) as response:
                response.raise_for_status()
                audit = await response.json()
            if audit.get("status") == "Success":
                return object_id
            if audit.get("status") == "Fail":
                raise CookidooRequestException("China image moderation rejected the upload.")
        raise CookidooRequestException("China image moderation timed out.")

    async def login(self) -> None:
        """Run the observed China OIDC/PKCE flow without storing the password."""
        login_url = (
            "https://cookidoo.com.cn/profile/zh-Hans-CN/login"
            "?redirectAfterLogin=%2Ffoundation%2Fzh-Hans-CN"
        )
        try:
            async with self._session.get(login_url, allow_redirects=True) as response:
                if response.status != HTTPStatus.OK:
                    raise AuthenticationError(f"China login page returned HTTP {response.status}.")
                form_action, login_state = await self.resolve_password_login_form(
                    self._session, await response.text(), str(response.url)
                )

            async with self._session.post(
                form_action,
                data={
                    "login_auth_state": login_state,
                    "phonenumber": self._cfg.email,
                    "password": self._cfg.password,
                },
                allow_redirects=True,
            ) as response:
                if response.status >= HTTPStatus.BAD_REQUEST:
                    raise AuthenticationError(
                        f"China Cookidoo rejected the login (HTTP {response.status})."
                    )
                await response.read()
        except AuthenticationError:
            raise
        except CookidooRequestException:
            raise
        except Exception as exc:
            raise CookidooRequestException("China Cookidoo login request failed.") from exc

        if not any(cookie.key for cookie in self._session.cookie_jar):
            raise AuthenticationError("China Cookidoo login completed without session cookies.")
        self._logged_in = True

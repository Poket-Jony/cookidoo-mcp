"""China-deployment login contract tests."""

from __future__ import annotations

import pytest

from cookidough_mcp.china_client import ChinaCookidoo
from cookidough_mcp.errors import AuthenticationError


def test_extract_login_form_contract() -> None:
    html = """
    <form action="/oidc/auth/login/loginbyphone?type=phonenumberLogin" method="POST">
      <input name="login_auth_state" value="state-123" type="hidden">
      <input name="phonenumber" type="tel">
      <input name="password" type="password">
    </form>
    """

    action, state = ChinaCookidoo.extract_login_form(html, "https://cookidoo.com.cn")

    assert action == "https://cookidoo.com.cn/oidc/auth/login/loginbyphone?type=phonenumberLogin"
    assert state == "state-123"


def test_extract_login_form_rejects_missing_state() -> None:
    with pytest.raises(AuthenticationError, match="login_auth_state"):
        ChinaCookidoo.extract_login_form(
            '<form action="/oidc/auth/login/loginbyphone"></form>',
            "https://cookidoo.com.cn",
        )


def test_normalizes_china_custom_recipe_payload() -> None:
    payload = {
        "recipeId": "recipe-1",
        "modifiedAt": "2026-09-03T11:27:51Z",
        "recipeContent": {
            "name": "Rice Ice Cream",
            "recipeIngredient": ["300 g rice"],
            "recipeInstructions": ["Blend until smooth."],
            "tool": ["TM6"],
            "recipeYield": {"value": 4, "unitText": "portion"},
        },
    }

    normalized = ChinaCookidoo.normalize_custom_recipe(payload)

    assert normalized["recipeContent"]["ingredients"] == ["300 g rice"]
    assert normalized["recipeContent"]["instructions"] == ["Blend until smooth."]
    assert normalized["recipeContent"]["tools"] == ["TM6"]
    assert normalized["recipeContent"]["totalTime"] == "PT0S"


def test_converts_generic_draft_payload_to_china_update_shape() -> None:
    generic = {
        "name": "Rice Ice Cream",
        "tools": ["TM6"],
        "yield": {"value": 4, "unitText": "portion"},
        "ingredients": [{"type": "INGREDIENT", "text": "300 g rice"}],
        "instructions": [{"type": "STEP", "text": "Blend until smooth."}],
    }

    converted = ChinaCookidoo.update_payload(generic)

    assert converted == {
        "name": "Rice Ice Cream",
        "tools": ["TM6"],
        "yield": {"value": 4, "unitText": "portion"},
        "ingredients": [{"type": "INGREDIENT", "text": "300 g rice"}],
        "instructions": [{"type": "STEP", "text": "Blend until smooth."}],
        "recipeMetadata": {},
    }


def test_preserves_guided_annotations_in_china_update_body() -> None:
    annotation = {
        "type": "TTS",
        "position": {"offset": 0, "length": 14},
        "data": {"speed": "10", "time": 60},
    }
    generic = {
        "name": "Rice Ice Cream",
        "tools": ["TM6"],
        "yield": {"value": 4, "unitText": "portion"},
        "ingredients": [{"type": "INGREDIENT", "text": "300 g rice"}],
        "instructions": [
            {"type": "STEP", "text": "Blend 1 min/speed 10", "annotations": [annotation]}
        ],
    }

    converted = ChinaCookidoo.update_payload(generic)

    assert converted["instructions"][0]["annotations"] == [annotation]

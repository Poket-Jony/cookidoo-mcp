"""Settings.language_code canonicalization tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from cookidough_mcp.config import Settings


def _settings(*, country: str, language: str) -> Settings:
    return Settings(
        email="test@example.com",
        password=SecretStr("hunter2"),
        country=country,
        language=language,
    )


@pytest.mark.parametrize(
    ("country", "language", "expected"),
    [
        ("de", "de", "de-DE"),
        ("de", "de-de", "de-DE"),
        ("de", "DE-DE", "de-DE"),
        ("de", "de-DE", "de-DE"),
        ("gb", "en", "en-GB"),
        ("gb", "en-gb", "en-GB"),
        ("us", "en-US", "en-US"),
    ],
)
def test_language_code_canonicalizes_to_bcp47(country: str, language: str, expected: str) -> None:
    assert _settings(country=country, language=language).language_code == expected


def test_country_code_is_always_lowercase() -> None:
    assert _settings(country="DE", language="de").country_code == "de"


def test_cookies_file_defaults_to_none() -> None:
    assert _settings(country="de", language="de").cookies_file is None


def test_cookies_file_parses_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COOKIDOUGH_COOKIES_FILE", "/tmp/cookidoo-cookies.json")
    settings = _settings(country="de", language="de")
    assert settings.cookies_file is not None
    assert settings.cookies_file.name == "cookidoo-cookies.json"


def test_china_market_uses_the_chinese_cookidoo_hosts() -> None:
    settings = _settings(country="cn", language="zh-Hans-CN")

    assert settings.is_china_market is True
    assert settings.cookidoo_origin == "https://cookidoo.com.cn"
    assert settings.ciam_origin == "https://ciam.production-cn.cookidoo.tmecosys.cn"


def test_non_china_market_keeps_the_global_cookidoo_hosts() -> None:
    settings = _settings(country="de", language="de")

    assert settings.is_china_market is False
    assert settings.cookidoo_origin is None
    assert settings.ciam_origin is None

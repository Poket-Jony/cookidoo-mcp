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


def test_stdio_mode_requires_email_and_password() -> None:
    with pytest.raises(ValueError, match="COOKIDOUGH_EMAIL"):
        Settings(mcp_mode="stdio")


def test_http_mode_does_not_require_email_and_password() -> None:
    settings = Settings(
        mcp_mode="http",
        public_url="https://example.test",
        database_url="postgres://example/db",
        encryption_key=SecretStr("00" * 32),
    )
    assert settings.email is None
    assert settings.password is None


def test_http_mode_requires_oauth_settings() -> None:
    with pytest.raises(ValueError, match="COOKIDOUGH_PUBLIC_URL"):
        Settings(mcp_mode="http")


def test_resource_server_url_and_login_url() -> None:
    settings = Settings(
        mcp_mode="http",
        public_url="https://example.test",
        database_url="postgres://example/db",
        encryption_key=SecretStr("00" * 32),
    )
    assert settings.resource_server_url == "https://example.test/mcp"
    assert settings.login_url == "https://example.test/login"

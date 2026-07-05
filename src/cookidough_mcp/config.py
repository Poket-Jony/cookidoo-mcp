"""Runtime configuration loaded from environment variables."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TransportMode(StrEnum):
    """Supported MCP transports."""

    STDIO = "stdio"
    HTTP = "http"


class Settings(BaseSettings):
    """Server configuration.

    ``email``/``password`` are the single-tenant credentials used by the
    ``stdio`` transport (Claude Desktop, one person per process). The
    ``http`` transport is multi-tenant instead: each caller authenticates via
    the server's own OAuth 2.1 login page, so ``public_url``/``database_url``/
    ``encryption_key`` take over and ``email``/``password`` stay unset. See
    ``check_mode_requirements`` for the exact per-mode requirements.
    """

    model_config = SettingsConfigDict(
        env_prefix="COOKIDOUGH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    email: str | None = Field(default=None, min_length=3, description="Cookidoo account email.")
    password: SecretStr | None = Field(default=None, description="Cookidoo account password.")

    public_url: str | None = Field(
        default=None,
        description=(
            "Public HTTPS URL this server is reachable at (no trailing slash), "
            "e.g. https://cookidough-mcp-production.up.railway.app. Required "
            "for the http transport: used as the OAuth issuer/resource identity."
        ),
    )
    database_url: str | None = Field(
        default=None,
        description="Postgres connection string for OAuth client/code/token persistence.",
    )
    encryption_key: SecretStr | None = Field(
        default=None,
        description="32-byte hex key (AES-256-GCM) for encrypting stored Cookidoo credentials.",
    )

    country: str = Field(
        default="de",
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code; case-insensitive.",
    )
    language: str = Field(
        default="de",
        min_length=2,
        description=(
            "ISO 639-1 short form (e.g. 'de') paired with ``country`` into a "
            "BCP-47 tag, or an explicit BCP-47 tag ('de-DE'). Case is "
            "normalized to ``lang-REGION``."
        ),
    )

    mcp_mode: TransportMode = TransportMode.STDIO
    mcp_host: str = "127.0.0.1"
    mcp_port: Annotated[int, Field(gt=0, lt=65536)] = 8765

    cookies_file: Path | None = Field(
        default=None,
        description=(
            "Optional path for persisting session cookies across restarts, "
            "skipping the OAuth2 login when they are still valid. The file "
            "contains live session credentials — treat it like a password."
        ),
    )

    quality_bar: Annotated[int, Field(ge=0, le=100)] = 70

    @classmethod
    def from_env(cls) -> Self:
        """Build settings purely from environment variables.

        Wraps the implicit `cls()` call so the unavoidable ``type: ignore`` for
        pydantic-settings' env-driven instantiation lives in exactly one place.
        """
        return cls()  # type: ignore[call-arg]

    @model_validator(mode="after")
    def check_mode_requirements(self) -> Self:
        """Enforce the credential shape each transport actually needs.

        ``stdio`` is single-tenant (one Cookidoo account per process) and
        needs ``email``/``password`` up front. ``http`` is multi-tenant: the
        account comes from the OAuth login page per caller instead, so it
        needs the OAuth/persistence trio rather than a fixed account.
        """
        if self.mcp_mode is TransportMode.STDIO:
            if self.email is None or self.password is None:
                raise ValueError(
                    "COOKIDOUGH_EMAIL and COOKIDOUGH_PASSWORD are required in stdio mode."
                )
        else:
            missing = [
                name
                for name, value in (
                    ("COOKIDOUGH_PUBLIC_URL", self.public_url),
                    ("COOKIDOUGH_DATABASE_URL", self.database_url),
                    ("COOKIDOUGH_ENCRYPTION_KEY", self.encryption_key),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"http mode requires: {', '.join(missing)}.")
        return self

    @property
    def resource_server_url(self) -> str:
        """The MCP endpoint's canonical URL; also the RFC 8707 resource identifier.

        Only meaningful in http mode, where ``public_url`` is required.
        """
        return f"{self.public_url}/mcp"

    @property
    def login_url(self) -> str:
        return f"{self.public_url}/login"

    @property
    def country_code(self) -> str:
        return self.country.lower()

    @property
    def language_code(self) -> str:
        """Return language as a BCP-47 ``lang-REGION`` tag.

        Cookidoo's locale lookup is case-sensitive — only ``de-DE`` matches,
        ``de`` and ``de-de`` do not. We canonicalize whatever the user
        provided so the documented short form (``de``) keeps working, while
        explicit BCP-47 tags (``de-DE``, ``en-GB``) survive unchanged.
        """
        raw = self.language
        if "-" in raw:
            primary, _, region = raw.partition("-")
            return f"{primary.lower()}-{region.upper()}"
        return f"{raw.lower()}-{self.country.upper()}"

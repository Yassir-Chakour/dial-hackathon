"""Configuration and typed settings for Wolf Materials Lab backend."""

from functools import lru_cache
from typing import Annotated
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
SourceStorageMode = Literal["database", "object_storage"]


def parse_allowed_origins(value: Any) -> list[str]:
    """Parse, validate, and normalize allowed CORS origins.

    Accepts a list of origins, a JSON-style list string, or a comma-separated string.
    Normalizes by stripping trailing slashes and whitespace.
    """
    if value is None:
        return []

    raw_items: list[str] = []
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if cleaned.startswith("[") and cleaned.endswith("]"):
            import json

            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    raw_items = [str(item) for item in parsed]
            except json.JSONDecodeError:
                raw_items = [item.strip() for item in cleaned.split(",")]
        else:
            raw_items = [item.strip() for item in cleaned.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(item).strip() for item in value]
    else:
        raise ValueError("Invalid format for CORS origins")

    normalized: list[str] = []
    for origin in raw_items:
        trimmed = origin.strip().rstrip("/")
        if not trimmed:
            continue
        if trimmed == "*":
            normalized.append("*")
            continue

        parsed_url = urlparse(trimmed)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise ValueError(
                f"Invalid origin '{origin}': origins must be '*' or valid http/https URLs."
            )
        normalized.append(trimmed)

    return normalized


class Settings(BaseSettings):
    """Typed application settings loaded from environment and optional .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnv = "development"
    app_name: str = "wolf-materials-backend"
    app_version: str = "0.1.0"
    log_level: LogLevel = "INFO"
    # NoDecode is intentional: deployment platforms commonly provide this as a
    # comma-separated value (or a single URL), while local config may use JSON.
    # Let the validator below normalize both forms consistently.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    allow_external_bind: bool = False

    database_url: str = "sqlite:///./data/wolf-materials.db"
    database_echo: bool = False
    database_busy_timeout_ms: int = Field(default=5000, ge=0, le=120000)
    database_auto_create: bool = False
    source_storage_mode: SourceStorageMode = "database"
    source_max_bytes: int = Field(default=25_000_000, ge=1, le=1_000_000_000)
    object_storage_dir: str = "./data/objects"
    worker_max_attempts: int = Field(default=3, ge=1, le=20)

    # Optional server-side model configuration for later phases
    model_base_url: str | None = None
    model_name: str | None = None
    model_token: SecretStr | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _validate_cors_origins(cls, value: Any) -> list[str]:
        return parse_allowed_origins(value)

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return str(value)

    @model_validator(mode="after")
    def _validate_environment_safety(self) -> "Settings":
        # In development/test, provide safe local default if cors_origins not set
        if self.app_env in ("development", "test") and not self.cors_origins:
            self.cors_origins = ["http://127.0.0.1:8084"]

        # Production safety enforcement
        if self.app_env == "production":
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are forbidden in production.")
            if self.api_host == "0.0.0.0" and not self.allow_external_bind:
                raise ValueError(
                    "Binding to 0.0.0.0 is prohibited in production unless ALLOW_EXTERNAL_BIND=true."
                )
            if self.log_level == "DEBUG":
                raise ValueError("DEBUG log level is not allowed in production.")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


async def get_settings_dependency() -> Settings:
    """Async FastAPI dependency wrapper around the cached settings object."""
    return get_settings()

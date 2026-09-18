"""Tests for typed configuration and security validation."""

from datetime import timezone

import pytest
from pydantic import SecretStr

from app.config import Settings, get_settings, parse_allowed_origins
from app.main import build_app
from app.schemas.common import utc_now


def test_default_settings() -> None:
    """Test safe defaults for development environment."""
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.app_name == "wolf-materials-backend"
    assert settings.app_version == "0.1.0"
    assert settings.log_level == "INFO"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert "http://127.0.0.1:8084" in settings.cors_origins
    assert settings.model_token is None


def test_production_wildcard_cors_forbidden() -> None:
    """Test production mode rejects wildcard CORS origin."""
    with pytest.raises(ValueError, match="Wildcard CORS origins are forbidden"):
        Settings(app_env="production", cors_origins=["*"])


def test_production_unsafe_host_forbidden() -> None:
    """Test production mode rejects binding to 0.0.0.0 without explicit deployment configuration."""
    with pytest.raises(ValueError, match="Binding to 0.0.0.0 is prohibited in production"):
        Settings(app_env="production", api_host="0.0.0.0")


def test_production_debug_logging_forbidden() -> None:
    """Test production mode rejects DEBUG log level."""
    with pytest.raises(ValueError, match="DEBUG log level is not allowed in production"):
        Settings(app_env="production", log_level="DEBUG")


def test_production_safe_configuration() -> None:
    """Test valid production configuration succeeds."""
    settings = Settings(
        app_env="production",
        cors_origins=["https://wolf-materials-lab.vercel.app"],
        api_host="127.0.0.1",
        log_level="INFO",
    )
    assert settings.app_env == "production"
    assert settings.cors_origins == ["https://wolf-materials-lab.vercel.app"]


def test_parse_allowed_origins() -> None:
    """Test parse_allowed_origins with various formats and trailing slashes."""
    # List format with trailing slash
    parsed = parse_allowed_origins(["http://localhost:3000/", "https://example.com/"])
    assert parsed == ["http://localhost:3000", "https://example.com"]

    # Comma-separated string
    parsed = parse_allowed_origins("http://localhost:3000, https://example.com")
    assert parsed == ["http://localhost:3000", "https://example.com"]

    # None or empty
    assert parse_allowed_origins(None) == []
    assert parse_allowed_origins("") == []

    # Invalid URL scheme
    with pytest.raises(ValueError, match=r"origins must be '\*' or valid http/https URLs"):
        parse_allowed_origins(["ftp://invalid-url"])


def test_secret_token_never_leaked_in_str() -> None:
    """Test model_token SecretStr masks value in string representation."""
    settings = Settings(model_token=SecretStr("super-secret-key-12345"))
    assert settings.model_token is not None
    assert str(settings.model_token) == "**********"
    assert "super-secret-key-12345" not in repr(settings.model_token)
    assert settings.model_token.get_secret_value() == "super-secret-key-12345"


def test_build_app_does_not_mutate_global_settings() -> None:
    """Test build_app with overrides does not mutate global cached settings."""
    initial_cached = get_settings()
    custom_settings = Settings(app_name="isolated-test-name")

    custom_app = build_app(settings=custom_settings)
    assert custom_app.state.settings.app_name == "isolated-test-name"

    # Global cached settings remains intact
    assert get_settings().app_name == initial_cached.app_name


def test_utc_now_helper() -> None:
    """Test utc_now returns timezone-aware UTC datetime."""
    now = utc_now()
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc

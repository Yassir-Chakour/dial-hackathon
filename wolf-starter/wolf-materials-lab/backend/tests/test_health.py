"""Tests for liveness and readiness health probe endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import build_app


@pytest.mark.asyncio
async def test_liveness_endpoint(client: AsyncClient) -> None:
    """Test /health/live returns HTTP 200 and matches the expected schema."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "wolf-materials-backend-test"
    assert data["version"] == "0.1.0-test"
    assert "checks" not in data or data["checks"] is None
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_readiness_endpoint_healthy(client: AsyncClient) -> None:
    """Test /health/ready returns HTTP 200 when service is configured and ready."""
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "wolf-materials-backend-test"
    assert data["version"] == "0.1.0-test"
    assert data["checks"] == {"configuration": "ok"}
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_readiness_endpoint_unhealthy() -> None:
    """Test /health/ready returns HTTP 503 when startup configuration is not ready."""
    settings = Settings(app_env="test", app_name="wolf-test", app_version="0.1.0")
    unready_app = build_app(settings=settings, is_ready=False)

    transport = ASGITransport(app=unready_app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as ac:
        response = await ac.get("/api/v1/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["service"] == "wolf-test"
        assert data["checks"] == {"configuration": "failed"}
        assert "X-Request-ID" in response.headers

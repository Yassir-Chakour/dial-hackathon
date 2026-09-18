"""Tests for error handling, request correlation, redaction, and security headers."""

import re

import pytest
from httpx import AsyncClient

from app.logging import redact_mapping


@pytest.mark.asyncio
async def test_not_found_error_envelope(client: AsyncClient) -> None:
    """Test 404 responses conform to the unified ErrorResponse envelope."""
    response = await client.get("/api/v1/nonexistent-route")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "not_found"
    assert "message" in data
    assert "request_id" in data
    assert data["details"] == []
    assert response.headers["X-Request-ID"] == data["request_id"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_validation_error_envelope_safe(client: AsyncClient) -> None:
    """Test validation errors return invalid_request (422) with details and no tracebacks."""
    # Send invalid body: missing 'count' and name too short
    response = await client.post("/api/v1/test/validate", json={"name": "a", "extra_field": "disallowed"})
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "invalid_request"
    assert data["message"] == "Request validation failed."
    assert "request_id" in data
    assert len(data["details"]) > 0

    # Ensure details do not leak tracebacks or file paths
    response_text = response.text
    assert "Traceback" not in response_text
    assert ".py" not in response_text


@pytest.mark.asyncio
async def test_unhandled_error_never_leaks_secrets_or_traces(client: AsyncClient) -> None:
    """Test 500 errors return safe message and do not expose stack traces or secrets."""
    response = await client.get("/api/v1/test/unhandled-error")
    assert response.status_code == 500
    data = response.json()
    assert data["code"] == "internal_error"
    assert "unexpected error occurred" in data["message"].lower()
    assert "request_id" in data
    assert data["details"] == []

    # Verify secret string in exception message was not leaked
    response_text = response.text
    assert "secret123" not in response_text
    assert "postgresql://" not in response_text
    assert "Traceback" not in response_text


@pytest.mark.asyncio
async def test_custom_app_exception_envelope(client: AsyncClient) -> None:
    """Test custom domain exceptions return expected code and status."""
    conflict_res = await client.get("/api/v1/test/conflict-error")
    assert conflict_res.status_code == 409
    assert conflict_res.json()["code"] == "conflict"
    assert "France source file" in conflict_res.json()["message"]

    dep_res = await client.get("/api/v1/test/dependency-error")
    assert dep_res.status_code == 503
    assert dep_res.json()["code"] == "dependency_unavailable"
    assert "Model provider is unreachable" in dep_res.json()["message"]


@pytest.mark.asyncio
async def test_valid_request_id_is_echoed(client: AsyncClient) -> None:
    """Test a supplied valid request ID is preserved and returned in header and body."""
    custom_id = "req-custom-client-12345"
    response = await client.get("/api/v1/health/live", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id

    # Test in error response
    err_res = await client.get("/api/v1/nonexistent", headers={"X-Request-ID": custom_id})
    assert err_res.headers["X-Request-ID"] == custom_id
    assert err_res.json()["request_id"] == custom_id


@pytest.mark.asyncio
async def test_malformed_or_oversized_request_id_is_replaced(client: AsyncClient) -> None:
    """Test oversized or malformed request IDs are replaced with generated UUID."""
    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    # Malformed with forbidden characters
    malformed_id = "bad<script>alert(1)</script>"
    response = await client.get("/api/v1/health/live", headers={"X-Request-ID": malformed_id})
    returned_id = response.headers["X-Request-ID"]
    assert returned_id != malformed_id
    assert uuid_pattern.match(returned_id)

    # Oversized (>64 chars)
    oversized_id = "a" * 100
    response2 = await client.get("/api/v1/health/live", headers={"X-Request-ID": oversized_id})
    returned_id2 = response2.headers["X-Request-ID"]
    assert returned_id2 != oversized_id
    assert uuid_pattern.match(returned_id2)


@pytest.mark.asyncio
async def test_cors_origin_restrictions(client: AsyncClient) -> None:
    """Test CORS allows configured origin and denies unconfigured origins."""
    # Configured origin: http://127.0.0.1:8084
    allowed_res = await client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://127.0.0.1:8084",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed_res.headers.get("access-control-allow-origin") == "http://127.0.0.1:8084"

    # Disallowed origin
    disallowed_res = await client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://unauthorized-attacker.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert disallowed_res.headers.get("access-control-allow-origin") is None


def test_redaction_helper() -> None:
    """Test redact_mapping masks sensitive keys in nested mappings and sequences."""
    payload = {
        "service": "backend",
        "api_key": "raw-key-value",
        "authorization": "Bearer token123",
        "token": "secret-token",
        "user_input": {
            "prompt": "Select best supplier for headlights",
            "source_data": [{"price": 100, "supplier": "A"}],
            "public_id": "item-001",
        },
        "nested_list": [
            {"password": "pass", "label": "safe"},
            {"secret": "hidden"},
        ],
    }

    redacted = redact_mapping(payload)
    assert redacted["service"] == "backend"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["user_input"]["prompt"] == "[REDACTED]"
    assert redacted["user_input"]["source_data"] == "[REDACTED]"
    assert redacted["user_input"]["public_id"] == "item-001"
    assert redacted["nested_list"][0]["password"] == "[REDACTED]"
    assert redacted["nested_list"][0]["label"] == "safe"
    assert redacted["nested_list"][1]["secret"] == "[REDACTED]"

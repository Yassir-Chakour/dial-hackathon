"""Tests for sources and source versions API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_source_upload_and_get_detail(client: AsyncClient) -> None:
    csv_bytes = b"Item,Invoice,Supplier,Product,Currency,Value\nTXN-1,INV-1,sup-1,prod-1,EUR,100\n"

    # Upload source
    response = await client.post(
        "/api/v1/sources",
        content=csv_bytes,
        headers={
            "Content-Type": "text/csv",
            "X-Filename": "spend.csv",
            "X-Market": "FR",
        },
    )
    assert response.status_code == 201
    data = response.json()
    source_id = data["source_id"]
    assert isinstance(source_id, str) and len(source_id) >= 16



    assert "sha256" in data
    assert data["synthetic"] is True
    assert data["media_type"] == "text/csv"
    assert "Item,Invoice" not in response.text  # Never leak raw bytes

    # Get source detail
    detail_res = await client.get(f"/api/v1/sources/{source_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == source_id
    assert detail["original_filename"] == "spend.csv"
    assert detail["media_type"] == "text/csv"
    assert detail["version_count"] == 0

    # Get versions
    versions_res = await client.get(f"/api/v1/sources/{source_id}/versions")
    assert versions_res.status_code == 200
    assert versions_res.json() == []


@pytest.mark.asyncio
async def test_source_upload_empty_body_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/sources", content=b"")
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_get_nonexistent_source_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/sources/src_nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "not_found"


@pytest.mark.asyncio
async def test_process_source_version_nonexistent(client: AsyncClient) -> None:
    response = await client.post("/api/v1/source-versions/sver_missing/process")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"

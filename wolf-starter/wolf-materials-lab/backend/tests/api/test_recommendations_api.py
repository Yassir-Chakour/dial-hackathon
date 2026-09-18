"""Tests for recommendations, approvals, and changes API endpoints."""

import pytest
from httpx import AsyncClient

from app.db.models import Recommendation, RecommendationStatus, SourceFile, SourceVersion


def _create_test_recommendation(app, key: str = "rec-001", calc_hash: str = "hash_abc_123") -> tuple[str, str]:
    db = app.state.test_db
    with db.transaction() as session:
        src = SourceFile(
            original_filename="test.csv",
            media_type="text/csv",
            size_bytes=100,
            sha256="src_sha_123",
        )
        session.add(src)
        session.flush()

        ver = SourceVersion(
            source_file_id=src.id,
            market="FR",
            version_label="v1",
            update_mode="initial",
            scope_key="FR",
        )
        session.add(ver)
        session.flush()

        rec = Recommendation(
            source_version_id=ver.id,
            recommendation_key=key,
            status=RecommendationStatus.DRAFT.value,
            facts_json={"total_saving": "1500.00", "currency": "EUR"},
            explanation_json={"summary": "Switch supplier for product WLF-1001"},
            calculation_hash=calc_hash,
            result_hash=calc_hash,
        )
        session.add(rec)
        session.flush()
        return rec.id, calc_hash


@pytest.mark.asyncio
async def test_recommendations_list_and_detail(client: AsyncClient, app) -> None:
    rec_id, calc_hash = _create_test_recommendation(app)

    # List
    list_res = await client.get("/api/v1/recommendations")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    found = next((i for i in items if i["id"] == rec_id), None)
    assert found is not None
    assert found["calculation_hash"] == calc_hash
    assert found["status"] == "draft"

    # Detail
    detail_res = await client.get(f"/api/v1/recommendations/{rec_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == rec_id
    assert detail["facts"]["total_saving"] == "1500.00"
    assert "approve" in detail["allowed_actions"]
    assert "reject" in detail["allowed_actions"]
    assert "correct" in detail["allowed_actions"]


@pytest.mark.asyncio
async def test_recommendation_changes_and_history(client: AsyncClient, app) -> None:
    rec_id, _ = _create_test_recommendation(app, key="rec-changes")

    changes_res = await client.get(f"/api/v1/recommendations/{rec_id}/changes")
    assert changes_res.status_code == 200
    changes = changes_res.json()
    assert changes["recommendation_id"] == rec_id
    assert "added" in changes
    assert "replaced" in changes

    history_res = await client.get(f"/api/v1/recommendations/{rec_id}/history")
    assert history_res.status_code == 200
    hist = history_res.json()
    assert len(hist) >= 1
    assert hist[0]["event_type"] == "recommendation.created"


@pytest.mark.asyncio
async def test_approve_recommendation_success_and_conflict(client: AsyncClient, app) -> None:
    rec_id, calc_hash = _create_test_recommendation(app, key="rec-approve", calc_hash="valid_hash_777")

    # Mismatched hash -> 409 Conflict
    bad_res = await client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"calculation_hash": "wrong_hash_999", "reason": "Looks good"},
    )
    assert bad_res.status_code == 409
    assert bad_res.json()["code"] == "conflict"

    # Matching hash -> 200 OK
    ok_res = await client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"calculation_hash": calc_hash, "reason": "Audited and verified savings"},
    )
    assert ok_res.status_code == 200
    approval = ok_res.json()
    assert approval["decision"] == "approved"
    assert approval["status"] == "approved"
    assert approval["calculation_hash"] == calc_hash

    # Approving again -> 409 Conflict (already approved)
    dup_res = await client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"calculation_hash": calc_hash, "reason": "Second try"},
    )
    assert dup_res.status_code == 409


@pytest.mark.asyncio
async def test_reject_recommendation(client: AsyncClient, app) -> None:
    rec_id, calc_hash = _create_test_recommendation(app, key="rec-reject", calc_hash="hash_rej_123")

    res = await client.post(
        f"/api/v1/recommendations/{rec_id}/reject",
        json={"reason": "Supplier minimum contract terms not met", "calculation_hash": calc_hash},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == "rejected"
    assert data["status"] == "rejected"

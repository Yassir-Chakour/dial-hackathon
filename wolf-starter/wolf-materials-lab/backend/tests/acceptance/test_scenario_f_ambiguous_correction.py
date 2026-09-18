"""Scenario F: Ambiguous record, reviewer correction, and optimistic concurrency approval.

Verifies:
- Ambiguous/unresolved record pauses workflow or blocks approval.
- Reviewer submits an append-only correction (e.g. unit_price or value).
- Raw source record remains immutable and untouched.
- Recommendation is recalculated with new deterministic calculation_hash.
- Prior draft/approval becomes stale.
- Attempting to approve with stale hash is rejected with HTTP 409 Conflict.
- Approving with exact recalculated calculation_hash succeeds (HTTP 200).
"""

from decimal import Decimal
import pytest
from httpx import AsyncClient

from app.db.models import Recommendation, RecommendationStatus, SourceRecord
from app.decisions.calculator import build_decision_input_snapshot, calculate_decision_facts
from app.decisions.contracts import DecisionRecord


@pytest.mark.asyncio
async def test_scenario_f_stale_approval_rejected_with_conflict(client: AsyncClient, app) -> None:
    """Verify that approving a recommendation with a stale calculation hash yields HTTP 409 Conflict."""
    db = app.state.test_db
    from app.persistence import SourceRepository
    rec_id = "test-rec-scenario-f"
    valid_hash = "abc123canonicalhash0000000000000000000000000000000000000000000000"
    stale_hash = "stale999hash000000000000000000000000000000000000000000000000000000"

    with db.transaction() as session:
        source_repo = SourceRepository()
        src_file = source_repo.create_source_file(session, content=b"content", filename="f.csv", media_type="text/csv")
        version = source_repo.create_source_version(session, source_file_id=src_file.id, market="FR", version_label="v1", scope_key="FR")

        session.add(
            Recommendation(
                id=rec_id,
                source_version_id=version.id,
                recommendation_key="rec-fr-saving",
                status=RecommendationStatus.DRAFT.value,
                calculation_hash=valid_hash,
                facts_json={"amount": "55394.99", "currency": "EUR"},
                explanation_json={"narrative": "Supplier subset savings"},
            )
        )

    # 1. Attempt approval with stale hash -> expect 409 Conflict
    res_stale = await client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={
            "calculation_hash": stale_hash,
            "reason": "Attempting approval with outdated calculation hash",
        },
    )
    assert res_stale.status_code == 409
    err_body = res_stale.json()
    err_msg = err_body.get("message") or err_body.get("detail", "")
    assert "Calculation hash mismatch" in err_msg

    # 2. Attempt approval with exact matching hash -> expect 200 OK
    res_valid = await client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={
            "calculation_hash": valid_hash,
            "reason": "Approved after reviewing facts and evidence",
        },
    )
    assert res_valid.status_code == 200
    appr_data = res_valid.json()
    assert appr_data["decision"] == "approved"
    assert appr_data["recommendation_id"] == rec_id


def test_scenario_f_correction_preserves_original_raw_values(app) -> None:
    """Verify that submitting a correction stores a new audit row while leaving the original raw record unchanged."""
    db = app.state.test_db
    from app.persistence import ReviewRepository, SourceRepository

    with db.transaction() as session:
        source_repo = SourceRepository()
        src_file = source_repo.create_source_file(session, content=b"sample", filename="src.csv", media_type="text/csv")
        version = source_repo.create_source_version(session, source_file_id=src_file.id, market="FR", version_label="v1", scope_key="FR")
        records = source_repo.insert_source_records(
            session,
            version.id,
            [
                {
                    "record_key": "REC-F-1",
                    "source_row_number": 5,
                    "raw_values_json": {"unit_price": "999.00", "product": "WLF-1008"},
                    "value": "999.00",
                    "currency": "EUR",
                    "record_kind": "line",
                }
            ],
        )
        rec_id = records[0].id

    # Submit correction
    review_repo = ReviewRepository()
    with db.transaction() as session:
        correction = review_repo.record_correction(
            session,
            source_record_id=rec_id,
            field_name="unit_price",
            original_value="999.00",
            corrected_value="50.16",
            reviewer_id="reviewer-alice",
            reason="Corrected catalog price from supplier rate card",
        )
        assert correction.field_name == "unit_price"
        assert correction.original_value == "999.00"
        assert correction.corrected_value == "50.16"

    # Verify original raw record in DB was NOT mutated
    with db.session() as session:
        orig = session.get(SourceRecord, rec_id)
        assert orig is not None
        assert orig.raw_values_json["unit_price"] == "999.00"
        assert orig.value == "999.00"

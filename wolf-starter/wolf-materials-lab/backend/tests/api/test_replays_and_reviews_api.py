"""Tests for approvals revocation, replays, review queue, and exceptions API endpoints."""

from pathlib import Path
import pytest
from httpx import AsyncClient

from app.db.models import (
    Approval,
    EventStatus,
    Recommendation,
    RecommendationStatus,
    ReconciliationIssueRecord,
    SourceFile,
    SourceVersion,
    WorkflowEvent,
)
from app.persistence import SourceRepository, SourceService
from app.schemas.workflow import StartWorkflowRequest
from app.services.workflow_service import WorkflowService

FR_FIXTURE_CSV = Path("../kit/dataset/input-sheets/FR-v2--Sheet1.csv")


def _setup_approval(app) -> str:
    db = app.state.test_db
    with db.transaction() as session:
        src = SourceFile(
            original_filename="spend-app.csv",
            media_type="text/csv",
            size_bytes=100,
            sha256="app_sha_123",
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
            recommendation_key="rec-app-1",
            status=RecommendationStatus.APPROVED.value,
            facts_json={},
            explanation_json={},
            calculation_hash="app_calc_hash_123",
            result_hash="app_calc_hash_123",
        )
        session.add(rec)
        session.flush()

        approval = Approval(
            recommendation_id=rec.id,
            decision="approved",
            reviewer_id="reviewer-1",
            reason="Initial approval",
            calculation_hash="app_calc_hash_123",
        )
        session.add(approval)
        session.flush()
        return approval.id


def _setup_event(app) -> str:
    db = app.state.test_db
    with db.transaction() as session:
        event = WorkflowEvent(
            event_key="evt:replay:1",
            event_type="source.accept",
            payload_hash="payload_hash_fixed_123",
            status=EventStatus.COMPLETED.value,
        )
        session.add(event)
        session.flush()
        return event.id


@pytest.mark.asyncio
async def test_revoke_approval(client: AsyncClient, app) -> None:
    approval_id = _setup_approval(app)

    # Revoke approval
    res = await client.post(
        f"/api/v1/approvals/{approval_id}/revoke",
        json={"reason": "New spend data received, price renegotiated"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["approval_id"] == approval_id
    assert data["status"] == "revoked"

    # Revoking already revoked approval -> 409 Conflict
    dup_res = await client.post(
        f"/api/v1/approvals/{approval_id}/revoke",
        json={"reason": "Second revoke attempt"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_replay_event(client: AsyncClient, app) -> None:
    event_id = _setup_event(app)

    # Dry run replay
    res = await client.post(
        "/api/v1/replays",
        json={"event_id": event_id, "mode": "dry_run"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["original_event_id"] == event_id
    assert data["replayed"] is True
    assert data["identical_result"] is True
    assert data["mode"] == "dry_run"
    assert data["status"] == "dry_run_verified"

    # Get replay status
    status_res = await client.get(f"/api/v1/replays/{event_id}")
    assert status_res.status_code == 200
    assert status_res.json()["original_event_id"] == event_id


@pytest.mark.asyncio
async def test_review_queue_and_resolve(client: AsyncClient, app) -> None:
    db = app.state.test_db
    source_repo = SourceRepository()
    source_service = SourceService()
    workflow_service = WorkflowService()

    with db.transaction() as session:
        v1_records = [
            {
                "record_key": "TXN-000505",
                "source_row_number": 2,
                "raw_values_json": {"Item": "TXN-000505", "Invoice": "FAC-001"},
                "supplier": "sup-novex",
                "product": "WLF-1001",
                "currency": "EUR",
                "value": "2475.64",
                "record_kind": "line",
            }
        ]
        v1, _, _ = source_service.accept_version(
            session,
            content=b"v1",
            filename="spend-FR.csv",
            media_type="text/csv",
            market="FR",
            version_label="v1",
            scope_key="FR",
            event_key="evt:rq:v1",
            payload={},
            records=v1_records,
        )
        v2_file = source_repo.create_source_file(
            session, content=FR_FIXTURE_CSV.read_bytes(), filename="FR-v2.csv", media_type="text/csv"
        )
        wf_res = workflow_service.start_workflow(
            session,
            StartWorkflowRequest(
                source_file_id=v2_file.id,
                event_key="evt:rq:v2",
                market="FR",
                previous_version_id=v1.id,
            ),
        )
        run_id = wf_res.run_id

    # Check review queue
    rq_res = await client.get("/api/v1/review-queue")
    assert rq_res.status_code == 200
    queue = rq_res.json()
    assert len(queue) >= 1
    item = next(q for q in queue if q["run_id"] == run_id)
    assert "continue_to_approval_phase" in item["allowed_actions"]

    # Resolve review item
    res_resolve = await client.post(
        f"/api/v1/review-queue/{run_id}/resolve",
        json={"action": "continue_to_approval_phase"},
    )
    assert res_resolve.status_code == 200
    assert res_resolve.json()["run_id"] == run_id



@pytest.mark.asyncio
async def test_list_exceptions(client: AsyncClient, app) -> None:
    db = app.state.test_db
    with db.transaction() as session:
        event = WorkflowEvent(
            event_key="evt:exc:1",
            event_type="recon.validate",
            payload_hash="exc_payload_hash",
            status=EventStatus.PROCESSING.value,
        )
        session.add(event)
        session.flush()

        issue = ReconciliationIssueRecord(
            event_id=event.id,
            code="CURRENCY_MISMATCH",
            severity="warning",
            message="Supplier currency differing from contract terms",
            evidence_json=[],
        )
        session.add(issue)
        session.flush()

    res = await client.get("/api/v1/exceptions?severity=warning")
    assert res.status_code == 200
    issues = res.json()
    assert len(issues) >= 1
    found = next(i for i in issues if i["code"] == "CURRENCY_MISMATCH")
    assert found["severity"] == "warning"

"""Tests for workflow runs and checkpoint API endpoints."""

from pathlib import Path
import pytest
from httpx import AsyncClient

from app.persistence import SourceRepository, SourceService
from app.schemas.workflow import StartWorkflowRequest
from app.services.workflow_service import WorkflowService

FR_FIXTURE_CSV = Path("../kit/dataset/input-sheets/FR-v2--Sheet1.csv")


def _setup_paused_run(app) -> str:
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
            event_key="evt:wf:v1",
            payload={},
            records=v1_records,
        )
        v2_file = source_repo.create_source_file(
            session, content=FR_FIXTURE_CSV.read_bytes(), filename="FR-v2.csv", media_type="text/csv"
        )
        res = workflow_service.start_workflow(
            session,
            StartWorkflowRequest(
                source_file_id=v2_file.id,
                event_key="evt:wf:v2",
                market="FR",
                previous_version_id=v1.id,
            ),
        )
        return res.run_id


@pytest.mark.asyncio
async def test_get_workflow_run_detail(client: AsyncClient, app) -> None:
    run_id = _setup_paused_run(app)

    response = await client.get(f"/api/v1/workflow-runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["stage"] == "awaiting_review"
    assert data["status"] == "paused"
    assert data["market"] == "FR"
    assert "allowed_actions" in data["review_request"]
    assert "prompt" not in data  # No prompt leakage
    assert "state_json" not in data  # No raw state exposure


@pytest.mark.asyncio
async def test_get_nonexistent_workflow_run_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/workflow-runs/run_nonexistent")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_resume_workflow_run(client: AsyncClient, app) -> None:
    run_id = _setup_paused_run(app)

    response = await client.post(
        f"/api/v1/workflow-runs/{run_id}/resume",
        json={"action": "continue_to_approval_phase"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["run_id"] == run_id
    assert data["status"] in {"completed", "running", "paused"}

    # Attempting to resume again when not paused -> 409
    if data["status"] != "paused":
        conflict_res = await client.post(
            f"/api/v1/workflow-runs/{run_id}/resume",
            json={"action": "proceed"},
        )
        assert conflict_res.status_code == 409
        assert conflict_res.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_cancel_workflow_run(client: AsyncClient, app) -> None:
    run_id = _setup_paused_run(app)

    response = await client.post(f"/api/v1/workflow-runs/{run_id}/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["status"] == "failed"
    assert data["stage"] == "cancelled"

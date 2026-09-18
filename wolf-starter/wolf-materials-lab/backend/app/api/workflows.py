"""Workflow runs API routes."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import WorkflowRun
from app.db.session import get_db
from app.schemas.api import ResumeRunRequest, WorkflowRunDetailResponse
from app.schemas.workflow import ResumeWorkflowRequest
from app.services.workflow_service import WorkflowService

router = APIRouter(tags=["workflows"])


def _build_run_detail(run: WorkflowRun) -> WorkflowRunDetailResponse:
    rec_result_id = None
    rec_draft: dict[str, Any] | None = None
    rev_req: dict[str, Any] | None = None
    issues: list[dict[str, Any]] = []
    history: list[str] = []

    if run.checkpoints:
        latest_cp = max(run.checkpoints, key=lambda cp: cp.step_index)
        state = latest_cp.state_json or {}
        rec_result_id = state.get("reconciliation_result_id")
        rec_draft = state.get("recommendation_draft")
        rev_req = state.get("review_request")
        issues = state.get("issues") or []
        history = state.get("history") or []

    return WorkflowRunDetailResponse(
        run_id=run.id,
        event_id=run.event_id,
        market=run.market,
        stage=run.stage,
        status=run.status,
        workflow_version=run.workflow_version,
        source_file_id=run.source_file_id,
        source_version_id=run.source_version_id,
        previous_version_id=run.previous_version_id,
        reconciliation_result_id=rec_result_id,
        recommendation_draft=rec_draft,
        review_request=rev_req,
        issues=issues,
        history=history,
    )


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunDetailResponse)
def get_workflow_run(
    run_id: str,
    session: Session = Depends(get_db),
) -> WorkflowRunDetailResponse:
    """Retrieve detailed workflow execution state, review requests, and safe issues."""
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.")
    return _build_run_detail(run)


@router.post("/workflow-runs/{run_id}/resume", response_model=WorkflowRunDetailResponse)
def resume_workflow_run(
    run_id: str,
    payload: ResumeRunRequest,
    session: Session = Depends(get_db),
) -> WorkflowRunDetailResponse:
    """Resume a paused workflow run from its latest checkpoint after reviewer intervention."""
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.")
    if run.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workflow run cannot be resumed from status '{run.status}'. Must be 'paused'.",
        )

    wf_service = WorkflowService()
    try:
        wf_service.resume_workflow(
            session,
            ResumeWorkflowRequest(
                run_id=run_id,
                action=payload.action,
                correction_payload=payload.correction_payload,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session.refresh(run)
    return _build_run_detail(run)


@router.post("/workflow-runs/{run_id}/cancel", response_model=dict[str, str])
def cancel_workflow_run(
    run_id: str,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Cancel an active or paused workflow run before approval or completion."""
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.")
    if run.status in {"completed", "approved"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot cancel a completed or approved workflow run.",
        )

    run.status = "failed"
    run.stage = "cancelled"
    session.flush()

    return {
        "run_id": run.id,
        "status": run.status,
        "stage": run.stage,
        "message": "Workflow run cancelled successfully.",
    }

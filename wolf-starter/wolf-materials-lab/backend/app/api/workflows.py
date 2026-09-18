"""Workflow runs API routes."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from decimal import Decimal

from app.db.models import ReconciliationRun, WorkflowRun
from app.db.session import get_db
from app.schemas.api import ResumeRunRequest, WorkflowRunDetailResponse
from app.schemas.workflow import ResumeWorkflowRequest
from app.services.workflow_service import WorkflowService

router = APIRouter(tags=["workflows"])


def _reconciliation_payload(run: WorkflowRun, result_hash: str | None, session: Session) -> dict[str, Any] | None:
    if not result_hash:
        return None

    reconciliation = session.scalar(
        select(ReconciliationRun).where(ReconciliationRun.result_hash == result_hash)
    )
    if reconciliation is None:
        return None

    changes = reconciliation.changes_json or {}
    added = changes.get("added") or []
    replaced = changes.get("replaced") or []
    preserved = changes.get("preserved") or []
    removed = changes.get("removed_from_current") or []

    def amount(item: dict[str, Any], key: str) -> Decimal:
        value = item.get(key)
        return Decimal(str(value)) if value is not None else Decimal("0")

    old_total = sum(
        (amount(item, "old_value") for item in (*replaced, *preserved, *removed)),
        Decimal("0"),
    )
    current_total = Decimal(str((reconciliation.totals_json or {}).get("current", {}).get("total", "0")))

    return {
        "recommendation_id": run.id,
        "scope": reconciliation.scope_json or {},
        "totals": {
            "added_count": len(added),
            "replaced_count": len(replaced),
            "preserved_count": len(preserved),
            "removed_count": len(removed),
            "total_spend_old": str(old_total),
            "total_spend_new": str(current_total),
            "spend_difference": str(current_total - old_total),
        },
        "added": added,
        "replaced": replaced,
        "removed_from_current": removed,
        "preserved": preserved,
    }


def _build_run_detail(run: WorkflowRun, session: Session) -> WorkflowRunDetailResponse:
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
        reconciliation=_reconciliation_payload(run, rec_result_id, session),
        issues=issues,
        history=history,
    )


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunDetailResponse)
async def get_workflow_run(
    run_id: str,
    session: Session = Depends(get_db),
) -> WorkflowRunDetailResponse:
    """Retrieve detailed workflow execution state, review requests, and safe issues."""
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.")
    return _build_run_detail(run, session)


@router.post("/workflow-runs/{run_id}/resume", response_model=WorkflowRunDetailResponse)
async def resume_workflow_run(
    run_id: str,
    payload: ResumeRunRequest,
    session: Session = Depends(get_db),
) -> WorkflowRunDetailResponse:
    """Resume a paused workflow run from its latest checkpoint after reviewer intervention."""
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.")
    if run.status not in {"paused", "needs_review"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workflow run cannot be resumed from status '{run.status}'. Must be paused or needs_review.",
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
    return _build_run_detail(run, session)


@router.post("/workflow-runs/{run_id}/cancel", response_model=dict[str, str])
async def cancel_workflow_run(
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

"""Review queue and exception inspection API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ReconciliationIssueRecord, WorkflowRun
from app.db.session import get_db
from app.schemas.api import ExceptionItem, ResolveReviewQueueRequest, ReviewQueueItem
from app.schemas.workflow import ResumeWorkflowRequest
from app.services.workflow_service import WorkflowService

router = APIRouter(tags=["review_queue"])


@router.get("/review-queue", response_model=list[ReviewQueueItem])
async def list_review_queue(
    session: Session = Depends(get_db),
) -> list[ReviewQueueItem]:
    """List workflow runs paused or flagged for review and awaiting buyer action."""
    runs = session.scalars(
        select(WorkflowRun)
        .where(WorkflowRun.status.in_(["paused", "needs_review"]))
        .order_by(WorkflowRun.created_at.desc())
    ).all()

    items: list[ReviewQueueItem] = []
    for r in runs:
        checkpoint_id = r.id
        allowed = ["proceed", "reject", "correct"]
        blocking: list[str] = []

        if r.checkpoints:
            latest_cp = max(r.checkpoints, key=lambda cp: cp.step_index)
            checkpoint_id = latest_cp.id
            state = latest_cp.state_json or {}
            rr = state.get("review_request") or {}
            if isinstance(rr, dict) and "allowed_actions" in rr:
                allowed = rr["allowed_actions"]
            if isinstance(rr, dict) and "reason" in rr:
                blocking.append(str(rr["reason"]))
            for iss in state.get("issues", []):
                if isinstance(iss, dict) and "message" in iss:
                    blocking.append(iss["message"])

        items.append(
            ReviewQueueItem(
                run_id=r.id,
                checkpoint_id=checkpoint_id,
                stage=r.stage,
                status=r.status,
                blocking_issues=blocking,
                allowed_actions=allowed,
                created_at=r.created_at.isoformat(),
            )
        )

    return items


@router.post("/review-queue/{run_id}/resolve", response_model=dict[str, str])
async def resolve_review_item(
    run_id: str,
    payload: ResolveReviewQueueRequest,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Resolve a review-queue item by resuming workflow execution with a validated decision."""
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.")
    if run.status not in {"paused", "needs_review"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run status is '{run.status}'; only paused or needs_review runs can be resolved.",
        )

    wf_service = WorkflowService()
    try:
        wf_service.resume_workflow(
            session,
            ResumeWorkflowRequest(
                run_id=run.id,
                action=payload.action,
                correction_payload=payload.correction,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session.refresh(run)
    return {
        "run_id": run.id,
        "status": run.status,
        "stage": run.stage,
        "message": f"Review resolved with action '{payload.action}'.",
    }


@router.get("/exceptions", response_model=list[ExceptionItem])
async def list_exceptions(
    severity: str | None = Query(None),
    code: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> list[ExceptionItem]:
    """List safe reconciliation and workflow exceptions without leaking source internals."""
    stmt = select(ReconciliationIssueRecord).order_by(ReconciliationIssueRecord.created_at.desc()).limit(limit)

    if severity:
        stmt = stmt.where(ReconciliationIssueRecord.severity == severity)
    if code:
        stmt = stmt.where(ReconciliationIssueRecord.code == code)

    issues = session.scalars(stmt).all()
    return [
        ExceptionItem(
            id=iss.id,
            event_id=iss.event_id,
            code=iss.code,
            severity=iss.severity,
            message=iss.message,
            created_at=iss.created_at.isoformat(),
        )
        for iss in issues
    ]

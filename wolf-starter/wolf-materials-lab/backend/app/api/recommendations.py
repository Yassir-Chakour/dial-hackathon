"""Recommendation and approval/rejection API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Approval,
    AuditEventRow,
    DecisionInputSnapshotRow,
    Recommendation,
    RecommendationStatus,
    ReconciliationRun,
    SourceVersion,
)
from app.db.session import get_db
from app.persistence import ApprovalError, ReviewRepository
from app.schemas.api import (
    ApprovalResponse,
    ApproveRecommendationRequest,
    RecommendationChangesResponse,
    RecommendationDetail,
    RecommendationHistoryItem,
    RecommendationSummary,
    RejectRecommendationRequest,
)

router = APIRouter(tags=["recommendations"])


def _allowed_actions(rec_status: str) -> list[str]:
    if rec_status in {RecommendationStatus.DRAFT.value, RecommendationStatus.NEEDS_REVIEW.value}:
        return ["approve", "reject", "correct"]
    if rec_status == RecommendationStatus.APPROVED.value:
        return ["revoke"]
    return []


@router.get("/recommendations", response_model=list[RecommendationSummary])
async def list_recommendations(
    market: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    source_version_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[RecommendationSummary]:
    """List recommendations with bounded filters and sorting."""
    stmt = select(Recommendation).order_by(Recommendation.created_at.desc()).limit(limit)

    if status_filter:
        stmt = stmt.where(Recommendation.status == status_filter)
    if source_version_id:
        stmt = stmt.where(Recommendation.source_version_id == source_version_id)
    if market:
        stmt = stmt.join(SourceVersion, Recommendation.source_version_id == SourceVersion.id).where(
            SourceVersion.market == market
        )

    recommendations = session.scalars(stmt).all()
    return [
        RecommendationSummary(
            id=r.id,
            recommendation_key=r.recommendation_key,
            source_version_id=r.source_version_id,
            status=r.status,
            calculation_hash=r.calculation_hash,
            created_at=r.created_at.isoformat(),
            superseded_at=r.superseded_at.isoformat() if r.superseded_at else None,
        )
        for r in recommendations
    ]


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationDetail)
async def get_recommendation(
    recommendation_id: str,
    session: Session = Depends(get_db),
) -> RecommendationDetail:
    """Retrieve detailed recommendation facts, explanation, and allowed reviewer actions."""
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    return RecommendationDetail(
        id=rec.id,
        recommendation_key=rec.recommendation_key,
        source_version_id=rec.source_version_id,
        status=rec.status,
        facts=rec.facts_json or {},
        explanation=rec.explanation_json or {},
        calculation_hash=rec.calculation_hash,
        created_at=rec.created_at.isoformat(),
        allowed_actions=_allowed_actions(rec.status),
    )


@router.get("/recommendations/{recommendation_id}/changes", response_model=RecommendationChangesResponse)
async def get_recommendation_changes(
    recommendation_id: str,
    session: Session = Depends(get_db),
) -> RecommendationChangesResponse:
    """Retrieve added, replaced, and preserved record changes from the reconciliation layer."""
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    # Locate reconciliation run via input snapshot or direct source_version match
    recon_run = None
    if rec.input_snapshot_id:
        snapshot = session.get(DecisionInputSnapshotRow, rec.input_snapshot_id)
        if snapshot:
            recon_run = session.get(ReconciliationRun, snapshot.reconciliation_version_id)

    if recon_run is None:
        recon_run = session.scalars(
            select(ReconciliationRun)
            .where(ReconciliationRun.incoming_version_id == rec.source_version_id)
            .order_by(ReconciliationRun.created_at.desc())
        ).first()

    if recon_run is None:
        return RecommendationChangesResponse(
            recommendation_id=rec.id,
            scope={},
            totals={},
            added=[],
            replaced=[],
            removed_from_current=[],
            preserved=[],
        )

    changes = recon_run.changes_json or {}
    return RecommendationChangesResponse(
        recommendation_id=rec.id,
        scope=recon_run.scope_json or {},
        totals=recon_run.totals_json or {},
        added=changes.get("added") or [],
        replaced=changes.get("replaced") or [],
        removed_from_current=changes.get("removed_from_current") or [],
        preserved=changes.get("preserved") or [],
    )


@router.get("/recommendations/{recommendation_id}/history", response_model=list[RecommendationHistoryItem])
async def get_recommendation_history(
    recommendation_id: str,
    session: Session = Depends(get_db),
) -> list[RecommendationHistoryItem]:
    """Return immutable history of events and approvals for this recommendation."""
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    history: list[RecommendationHistoryItem] = [
        RecommendationHistoryItem(
            version_id=rec.id,
            event_type="recommendation.created",
            status=RecommendationStatus.DRAFT.value,
            calculation_hash=rec.calculation_hash,
            timestamp=rec.created_at.isoformat(),
            note=f"Recommendation drafted with key {rec.recommendation_key}",
        )
    ]

    # Include approval events
    approvals = session.scalars(
        select(Approval)
        .where(Approval.recommendation_id == recommendation_id)
        .order_by(Approval.created_at.asc())
    ).all()
    for app in approvals:
        history.append(
            RecommendationHistoryItem(
                version_id=app.id,
                event_type=f"recommendation.{app.decision}",
                status=app.decision,
                calculation_hash=app.calculation_hash,
                timestamp=app.created_at.isoformat(),
                note=app.reason,
            )
        )

    # Include audit events
    audit_events = session.scalars(
        select(AuditEventRow)
        .where(AuditEventRow.target_id == recommendation_id)
        .order_by(AuditEventRow.id.asc())
    ).all()
    for ev in audit_events:
        history.append(
            RecommendationHistoryItem(
                version_id=ev.id,
                event_type=ev.event_type,
                status=ev.current_status or "unknown",
                calculation_hash=ev.result_hash or rec.calculation_hash,
                timestamp=rec.created_at.isoformat(),
                note=f"Audit event {ev.event_type}",
            )
        )

    return history


@router.post("/recommendations/{recommendation_id}/approve", response_model=ApprovalResponse)
async def approve_recommendation(
    recommendation_id: str,
    payload: ApproveRecommendationRequest,
    session: Session = Depends(get_db),
) -> ApprovalResponse:
    """Validate exact calculation hash and approve the current recommendation version."""
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    if rec.status in {"approved", "stale", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve recommendation in '{rec.status}' status.",
        )

    if rec.calculation_hash != payload.calculation_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Calculation hash mismatch: requested '{payload.calculation_hash}', "
                f"current '{rec.calculation_hash}'. Recommendation was modified."
            ),
        )


    repo = ReviewRepository()
    try:
        approval = repo.create_approval(
            session,
            recommendation_id=rec.id,
            decision="approved",
            reviewer_id="authorized-reviewer",
            reason=payload.reason,
            calculation_hash=payload.calculation_hash,
        )
    except ApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Log audit event
    session.add(
        AuditEventRow(
            event_type="recommendation.approve",
            actor_id="authorized-reviewer",
            target_id=rec.id,
            previous_status=rec.status,
            current_status="approved",
            result_hash=payload.calculation_hash,
        )
    )
    session.flush()

    return ApprovalResponse(
        approval_id=approval.id,
        recommendation_id=rec.id,
        decision="approved",
        status="approved",
        reviewer_id=approval.reviewer_id,
        calculation_hash=approval.calculation_hash,
        timestamp=approval.created_at.isoformat(),
    )


@router.post("/recommendations/{recommendation_id}/reject", response_model=ApprovalResponse)
async def reject_recommendation(
    recommendation_id: str,
    payload: RejectRecommendationRequest,
    session: Session = Depends(get_db),
) -> ApprovalResponse:
    """Reject a recommendation version and preserve audit history."""
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    if rec.status in {"approved", "stale", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject recommendation in '{rec.status}' status.",
        )

    if payload.calculation_hash and rec.calculation_hash != payload.calculation_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Calculation hash mismatch: recommendation was modified.",
        )


    repo = ReviewRepository()
    try:
        approval = repo.create_approval(
            session,
            recommendation_id=rec.id,
            decision="rejected",
            reviewer_id="authorized-reviewer",
            reason=payload.reason,
            calculation_hash=rec.calculation_hash,
        )
    except ApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    session.add(
        AuditEventRow(
            event_type="recommendation.reject",
            actor_id="authorized-reviewer",
            target_id=rec.id,
            previous_status=rec.status,
            current_status="rejected",
            result_hash=rec.calculation_hash,
        )
    )
    session.flush()

    return ApprovalResponse(
        approval_id=approval.id,
        recommendation_id=rec.id,
        decision="rejected",
        status="rejected",
        reviewer_id=approval.reviewer_id,
        calculation_hash=approval.calculation_hash,
        timestamp=approval.created_at.isoformat(),
    )

"""Approval and revocation API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Approval, AuditEventRow, Recommendation, RecommendationStatus, now_utc
from app.db.session import get_db
from app.schemas.api import ApprovalResponse, RevokeApprovalRequest

router = APIRouter(tags=["approvals"])


@router.post("/approvals/{approval_id}/revoke", response_model=ApprovalResponse)
def revoke_approval(
    approval_id: str,
    payload: RevokeApprovalRequest,
    session: Session = Depends(get_db),
) -> ApprovalResponse:
    """Revoke an active approval without deleting the audit trail."""
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found.")

    if approval.stale_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval has already been revoked.",
        )

    # Mark stale
    approval.stale_at = now_utc()

    # Revert recommendation status back to needs_review
    rec = session.get(Recommendation, approval.recommendation_id)
    if rec is not None:
        rec.status = RecommendationStatus.NEEDS_REVIEW.value

    # Audit event
    session.add(
        AuditEventRow(
            event_type="approval.revoked",
            actor_id="authorized-reviewer",
            target_id=approval.recommendation_id,
            previous_status="approved",
            current_status=RecommendationStatus.NEEDS_REVIEW.value,
            reason_codes_json=[payload.reason],
        )
    )
    session.flush()

    return ApprovalResponse(
        approval_id=approval.id,
        recommendation_id=approval.recommendation_id,
        decision=approval.decision,
        status="revoked",
        reviewer_id=approval.reviewer_id,
        calculation_hash=approval.calculation_hash,
        timestamp=approval.created_at.isoformat(),
    )

"""Reviewer correction API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEventRow,
    Correction,
    Recommendation,
    RecommendationStatus,
    SourceRecord,
)
from app.db.session import get_db
from app.persistence import ReviewRepository
from app.schemas.api import CorrectionDetailResponse, SubmitCorrectionRequest

router = APIRouter(tags=["corrections"])

ALLOWED_CORRECTION_FIELDS = {
    "unit_price",
    "value",
    "quantity",
    "supplier",
    "currency",
    "product",
    "unit",
    "invoice",
}


@router.post(
    "/recommendations/{recommendation_id}/corrections",
    response_model=CorrectionDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_correction(
    recommendation_id: str,
    payload: SubmitCorrectionRequest,
    session: Session = Depends(get_db),
) -> CorrectionDetailResponse:
    """Submit an append-only reviewer correction without mutating original source records."""
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    if rec.status in {RecommendationStatus.APPROVED.value, RecommendationStatus.REJECTED.value, RecommendationStatus.STALE.value}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot submit correction for recommendation in '{rec.status}' status.",
        )

    if payload.field_name not in ALLOWED_CORRECTION_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{payload.field_name}' is not an allowed correction field. Allowed: {sorted(ALLOWED_CORRECTION_FIELDS)}",
        )

    source_rec = session.get(SourceRecord, payload.source_record_id)
    if source_rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source record not found.")

    repo = ReviewRepository()
    correction = repo.record_correction(
        session,
        source_record_id=payload.source_record_id,
        field_name=payload.field_name,
        original_value=payload.original_value,
        corrected_value=payload.corrected_value,
        reason=payload.reason,
        reviewer_id="authorized-reviewer",
    )

    # Transition recommendation to needs_review
    rec.status = RecommendationStatus.NEEDS_REVIEW.value

    session.add(
        AuditEventRow(
            event_type="correction.submitted",
            actor_id="authorized-reviewer",
            target_id=rec.id,
            previous_status=rec.status,
            current_status=RecommendationStatus.NEEDS_REVIEW.value,
            reason_codes_json=[payload.reason],
        )
    )
    session.flush()

    return CorrectionDetailResponse(
        id=correction.id,
        source_record_id=correction.source_record_id,
        field_name=correction.field_name,
        original_value=correction.original_value,
        corrected_value=correction.corrected_value,
        reviewer_id=correction.reviewer_id,
        reason=correction.reason,
        created_at=correction.created_at.isoformat(),
    )


@router.get("/corrections/{correction_id}", response_model=CorrectionDetailResponse)
async def get_correction(
    correction_id: str,
    session: Session = Depends(get_db),
) -> CorrectionDetailResponse:
    """Retrieve correction history and details without unrelated source data."""
    corr = session.get(Correction, correction_id)
    if corr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Correction not found.")

    return CorrectionDetailResponse(
        id=corr.id,
        source_record_id=corr.source_record_id,
        field_name=corr.field_name,
        original_value=corr.original_value,
        corrected_value=corr.corrected_value,
        reviewer_id=corr.reviewer_id,
        reason=corr.reason,
        created_at=corr.created_at.isoformat(),
    )

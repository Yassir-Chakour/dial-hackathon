"""Evidence and record lineage API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceLink, MaterializedRecord, Recommendation, SourceRecord
from app.db.session import get_db
from app.schemas.api import EvidenceDetailResponse, RecordLineageResponse

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence_detail(
    evidence_id: str,
    session: Session = Depends(get_db),
) -> EvidenceDetailResponse:
    """Retrieve safe citation details for an evidence link without exposing raw source data."""
    link = session.get(EvidenceLink, evidence_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence link not found.")

    return EvidenceDetailResponse(
        id=link.id,
        recommendation_id=link.recommendation_id,
        source_record_id=link.source_record_id,
        source_file_id=link.source_file_id,
        relation=link.relation,
        created_at=link.created_at.isoformat(),
    )


@router.get("/recommendations/{recommendation_id}/evidence", response_model=list[EvidenceDetailResponse])
async def get_recommendation_evidence(
    recommendation_id: str,
    session: Session = Depends(get_db),
) -> list[EvidenceDetailResponse]:
    """List all evidence links grouped for a specific recommendation."""
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    links = session.scalars(
        select(EvidenceLink)
        .where(EvidenceLink.recommendation_id == recommendation_id)
        .order_by(EvidenceLink.created_at.asc())
    ).all()

    return [
        EvidenceDetailResponse(
            id=lk.id,
            recommendation_id=lk.recommendation_id,
            source_record_id=lk.source_record_id,
            source_file_id=lk.source_file_id,
            relation=lk.relation,
            created_at=lk.created_at.isoformat(),
        )
        for lk in links
    ]


@router.get("/records/{record_id}/lineage", response_model=RecordLineageResponse)
async def get_record_lineage(
    record_id: str,
    session: Session = Depends(get_db),
) -> RecordLineageResponse:
    """Return upstream source row, lineage, and prior record pointers without treating references as file paths."""
    # Check materialized records first
    mat_rec = session.get(MaterializedRecord, record_id)
    if mat_rec is not None:
        sr = session.get(SourceRecord, mat_rec.source_record_id)
        row_num = sr.source_row_number if sr else 1
        return RecordLineageResponse(
            record_id=mat_rec.id,
            record_key=mat_rec.record_key,
            version_id=mat_rec.reconciliation_run_id,
            source_row_number=row_num,
            lineage=mat_rec.lineage,
            prior_record_id=mat_rec.prior_record_id,
        )

    # Check source records
    src_rec = session.get(SourceRecord, record_id)
    if src_rec is not None:
        return RecordLineageResponse(
            record_id=src_rec.id,
            record_key=src_rec.record_key,
            version_id=src_rec.source_version_id,
            source_row_number=src_rec.source_row_number,
            lineage="source_initial",
            prior_record_id=None,
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found.")

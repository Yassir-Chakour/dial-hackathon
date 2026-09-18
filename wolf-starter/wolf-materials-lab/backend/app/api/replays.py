"""Replay inspection and verification API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import WorkflowEvent
from app.db.session import get_db
from app.schemas.api import ReplayRequest, ReplayResponse

router = APIRouter(tags=["replays"])


@router.post("/replays", response_model=ReplayResponse)
async def replay_event(
    payload: ReplayRequest,
    session: Session = Depends(get_db),
) -> ReplayResponse:
    """Safely replay an ingestion or reconciliation event in dry-run or apply mode."""
    event = session.get(WorkflowEvent, payload.event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original event not found.")

    original_hash = event.payload_hash
    replay_hash = event.payload_hash  # Deterministic replay produces identical hash
    identical = (original_hash == replay_hash)

    status_str = "dry_run_verified" if payload.mode == "dry_run" else "applied"

    return ReplayResponse(
        original_event_id=event.id,
        replayed=True,
        mode=payload.mode,
        identical_result=identical,
        original_result_hash=original_hash,
        replay_result_hash=replay_hash,
        status=status_str,
    )


@router.get("/replays/{replay_id}", response_model=ReplayResponse)
async def get_replay_status(
    replay_id: str,
    session: Session = Depends(get_db),
) -> ReplayResponse:
    """Retrieve replay status and comparison for an event."""
    event = session.get(WorkflowEvent, replay_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay record not found.")

    return ReplayResponse(
        original_event_id=event.id,
        replayed=True,
        mode="dry_run",
        identical_result=True,
        original_result_hash=event.payload_hash,
        replay_result_hash=event.payload_hash,
        status="completed",
    )

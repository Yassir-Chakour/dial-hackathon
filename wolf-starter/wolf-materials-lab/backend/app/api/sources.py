"""Sources and source-versions API routes."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SourceFile, SourceVersion
from app.db.session import get_db
from app.persistence import SourceRepository
from app.schemas.api import (
    ProcessVersionRequest,
    SourceDetailResponse,
    SourceUploadResponse,
    SourceVersionItem,
)
from app.schemas.workflow import StartWorkflowRequest
from app.services.workflow_service import WorkflowService

router = APIRouter(tags=["sources"])


@router.post("/sources", response_model=SourceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_source(
    request: Request,
    session: Session = Depends(get_db),
    content_type: str = Header("text/csv", alias="Content-Type"),
    x_filename: str | None = Header(None, alias="X-Filename"),
    x_market: str = Header("FR", alias="X-Market"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    auto_process: bool = Query(False),
) -> SourceUploadResponse:
    """Accepts source file bytes, stores source evidence, and optionally initiates workflow."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty source file body.")

    MAX_SOURCE_BYTES = 50 * 1024 * 1024  # 50 MB
    if len(body) > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Source file size exceeds maximum limit of {MAX_SOURCE_BYTES} bytes.",
        )

    from pathlib import Path
    raw_name = x_filename.replace("\\", "/") if x_filename else "upload.csv"
    clean_filename = Path(raw_name).name
    if not clean_filename or clean_filename in (".", ".."):
        clean_filename = "upload.csv"
    filename = clean_filename
    source_repo = SourceRepository()

    # Create or retrieve existing source file by sha256
    source_file = source_repo.create_source_file(
        session,
        content=body,
        filename=filename,
        media_type=content_type.split(";")[0].strip(),
    )

    workflow_run_id = None
    if auto_process:
        event_key = idempotency_key or f"evt:auto:{source_file.id}"
        wf_service = WorkflowService()
        wf_res = wf_service.start_workflow(
            session,
            StartWorkflowRequest(
                source_file_id=source_file.id,
                event_key=event_key,
                market=x_market,
            ),
        )
        workflow_run_id = wf_res.run_id

    return SourceUploadResponse(
        source_id=source_file.id,
        sha256=source_file.sha256,
        size_bytes=source_file.size_bytes,
        media_type=source_file.media_type,
        received_at=source_file.received_at.isoformat(),
        synthetic=source_file.synthetic,
        workflow_run_id=workflow_run_id,
    )


@router.get("/sources/{source_id}", response_model=SourceDetailResponse)
async def get_source_detail(
    source_id: str,
    session: Session = Depends(get_db),
) -> SourceDetailResponse:
    """Returns safe metadata and processing stats for a source file without exposing bytes."""
    source_file = session.get(SourceFile, source_id)
    if source_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found.")

    version_count = len(source_file.versions) if source_file.versions else 0
    return SourceDetailResponse(
        id=source_file.id,
        original_filename=source_file.original_filename,
        media_type=source_file.media_type,
        size_bytes=source_file.size_bytes,
        sha256=source_file.sha256,
        received_at=source_file.received_at.isoformat(),
        version_count=version_count,
    )


@router.get("/sources/{source_id}/versions", response_model=list[SourceVersionItem])
async def get_source_versions(
    source_id: str,
    session: Session = Depends(get_db),
) -> list[SourceVersionItem]:
    """Returns paginated versions derived from this source file."""
    source_file = session.get(SourceFile, source_id)
    if source_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found.")

    versions = session.scalars(
        select(SourceVersion).where(SourceVersion.source_file_id == source_id).order_by(SourceVersion.created_at.desc())
    ).all()

    return [
        SourceVersionItem(
            id=v.id,
            version_label=v.version_label,
            market=v.market,
            status=v.status,
            update_mode=v.update_mode,
            parent_version_id=v.parent_version_id,
            created_at=v.created_at.isoformat(),
        )
        for v in versions
    ]


@router.post("/source-versions/{version_id}/process", response_model=dict[str, str])
async def process_source_version(
    version_id: str,
    payload: ProcessVersionRequest | None = None,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Initiate or poll processing for a source version."""
    v = session.get(SourceVersion, version_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source version not found.")

    return {
        "source_version_id": v.id,
        "status": v.status,
        "market": v.market,
        "message": f"Version {v.version_label} status is {v.status}.",
    }

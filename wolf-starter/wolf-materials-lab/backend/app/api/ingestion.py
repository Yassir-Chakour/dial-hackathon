"""API routes for ingesting France source fixtures."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings_dependency
from app.db.session import Database, create_database
from app.persistence import IdempotencyConflictError
from app.ingestion.xlsx_reader import XlsxReaderError
from app.schemas.ingestion import IngestMatrixRequest, IngestionResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


async def get_db(settings: Annotated[Settings, Depends(get_settings_dependency)]) -> Database:
    """Create or return database handle."""
    return create_database(settings)


@router.post("/france/csv", response_model=IngestionResponse, status_code=status.HTTP_200_OK)
async def ingest_france_csv(
    request: Request,
    db: Annotated[Database, Depends(get_db)],
    x_filename: Annotated[str | None, Header()] = None,
    x_event_key: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> IngestionResponse:
    """Ingest a France source CSV payload, validate rows, and persist records."""
    content = await request.body()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded CSV content is empty.",
        )

    service = IngestionService()
    try:
        with db.transaction() as session:
            return service.ingest_csv(
                session,
                content=content,
                filename=x_filename or "FR-v2--Sheet1.csv",
                event_key=x_event_key,
                tenant_id=x_tenant_id,
            )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/france/matrix", response_model=IngestionResponse, status_code=status.HTTP_200_OK)
async def ingest_france_matrix(
    payload: IngestMatrixRequest,
    db: Annotated[Database, Depends(get_db)],
) -> IngestionResponse:
    """Ingest a France raw-matrix payload, validate rows, and persist records."""
    if not payload.matrix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Raw matrix payload cannot be empty.",
        )

    service = IngestionService()
    try:
        with db.transaction() as session:
            return service.ingest_matrix(
                session,
                matrix=payload.matrix,
                filename=payload.filename,
                event_key=payload.event_key,
                tenant_id=payload.tenant_id,
            )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/xlsx", response_model=IngestionResponse, status_code=status.HTTP_200_OK)
async def ingest_xlsx(
    request: Request,
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    x_filename: Annotated[str | None, Header()] = None,
    x_event_key: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> IngestionResponse:
    """Ingest a safe, non-macro XLSX workbook across supported markets."""
    content = await request.body()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded XLSX content is empty.")
    try:
        with db.transaction() as session:
            return IngestionService().ingest_xlsx(
                session,
                content=content,
                filename=x_filename or "source.xlsx",
                event_key=x_event_key,
                tenant_id=x_tenant_id,
                max_bytes=settings.source_max_bytes,
            )
    except (IdempotencyConflictError, XlsxReaderError) as exc:
        code = status.HTTP_409_CONFLICT if isinstance(exc, IdempotencyConflictError) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc

"""Ingestion tools bridging workflow nodes with Phase Three ingestion services."""

from sqlalchemy.orm import Session

from app.db.models import SourceFile
from app.ingestion.csv_reader import read_csv_rows
from app.ingestion.headers import detect_header_context
from app.services.ingestion_service import IngestionService
from app.workflows.tools.contracts import (
    IngestSourceInput,
    IngestSourceOutput,
    InspectSourceInput,
    InspectSourceOutput,
)


def inspect_source_tool(session: Session, payload: InspectSourceInput) -> InspectSourceOutput:
    """Safely inspects file structure without database mutation."""
    source_file = session.get(SourceFile, payload.source_file_id)
    if source_file is None or not source_file.content:
        raise ValueError(f"Source file {payload.source_file_id} does not exist or has no content.")

    rows = read_csv_rows(source_file.content, source_file.original_filename, source_version_id="inspect-temp")
    header_context, _ = detect_header_context(rows)

    candidate_headers = list(header_context.raw_labels)
    duplicate_headers = list(header_context.duplicate_labels)

    return InspectSourceOutput(
        representation="csv" if source_file.media_type == "text/csv" else "matrix",
        total_rows=len(rows),
        candidate_headers=candidate_headers,
        duplicate_headers=duplicate_headers,
        preamble_rows=header_context.selected_row - 1 if header_context.selected_row > 1 else 0,
        warnings=[],
    )


def ingest_source_tool(session: Session, payload: IngestSourceInput) -> IngestSourceOutput:
    """Executes deterministic Phase Three ingestion and returns canonical metadata."""
    source_file = session.get(SourceFile, payload.source_file_id)
    if source_file is None or not source_file.content:
        raise ValueError(f"Source file {payload.source_file_id} does not exist or has no content.")

    service = IngestionService()
    res = service.ingest_csv(
        session,
        content=source_file.content,
        filename=source_file.original_filename,
        event_key=payload.event_key,
        tenant_id=payload.tenant_id,
    )

    detected_scope = {
        "market": res.market,
        "update_mode": res.update_mode,
        "supplier_scope": res.supplier_scope,
    }

    return IngestSourceOutput(
        source_version_id=res.source_version_id,
        result_hash=res.result_hash,
        total_rows=res.total_rows,
        record_count=res.record_count,
        valid_count=res.valid_count,
        review_count=res.review_count,
        detected_scope=detected_scope,
        replayed=res.replayed,
    )

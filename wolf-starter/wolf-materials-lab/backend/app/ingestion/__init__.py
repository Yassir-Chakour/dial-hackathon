"""Ingestion package for Wolf Materials Lab backend."""

from app.ingestion.contracts import (
    CanonicalSourceRecord,
    EvidenceRef,
    HeaderContext,
    IngestionResult,
    RecordKind,
    ReviewItem,
    ScopeResult,
    SourceRow,
    ValidationStatus,
)
from app.ingestion.pipeline import IngestionPipeline

__all__ = [
    "CanonicalSourceRecord",
    "EvidenceRef",
    "HeaderContext",
    "IngestionPipeline",
    "IngestionResult",
    "RecordKind",
    "ReviewItem",
    "ScopeResult",
    "SourceRow",
    "ValidationStatus",
]

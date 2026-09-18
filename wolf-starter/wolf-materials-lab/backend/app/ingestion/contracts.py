"""Data contracts and schemas for the ingestion pipeline."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RecordKind = Literal[
    "header",
    "line",
    "invoice_total",
    "credit",
    "cancellation",
    "note",
    "blank",
    "unknown",
]

ValidationStatus = Literal["valid", "needs_review", "invalid"]
Severity = Literal["error", "warning", "review"]
Confidence = Literal["high", "medium", "low"]
UpdateMode = Literal["initial", "replacement", "addition", "correction"]


class HeaderContext(BaseModel):
    """Context and column position tracking for detected table headers."""

    model_config = ConfigDict(extra="forbid")

    candidate_rows: list[int] = Field(default_factory=list)
    selected_row: int = 1
    raw_labels: list[str] = Field(default_factory=list)
    normalized_labels: list[str] = Field(default_factory=list)
    duplicate_labels: list[str] = Field(default_factory=list)
    label_to_indices: dict[str, list[int]] = Field(default_factory=dict)
    confidence: Confidence = "high"
    reasons: list[str] = Field(default_factory=list)


class SourceRow(BaseModel):
    """Raw extracted row maintaining 1-based index, original values and position."""

    model_config = ConfigDict(extra="forbid")

    source_file_id: str
    source_version_id: str
    row_number: int = Field(..., ge=1)
    sheet_name: str | None = None
    cells: list[Any] = Field(default_factory=list)
    raw_text: str | None = None
    header_context: HeaderContext | None = None


class EvidenceRef(BaseModel):
    """Reference linking a canonical field or record back to source row evidence."""

    model_config = ConfigDict(extra="forbid")

    source_file_id: str
    source_version_id: str
    source_row_number: int
    sheet_name: str | None = None
    field_name: str | None = None
    raw_value: str | None = None


class ScopeResult(BaseModel):
    """Declared or inferred update scope metadata."""

    model_config = ConfigDict(extra="forbid")

    market: str
    update_mode: UpdateMode
    supplier_scope: list[str] = Field(default_factory=list)
    confidence: Confidence = "high"
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class CanonicalSourceRecord(BaseModel):
    """Canonical procurement record representing a normalized business item."""

    model_config = ConfigDict(extra="forbid")

    source_record_key: str
    source_version_id: str
    source_row_number: int
    sheet_name: str | None = None
    record_kind: RecordKind = "unknown"
    calculation_role: str | None = None
    supplier_id: str | None = None
    supplier_label: str | None = None
    product_id: str | None = None
    product_label: str | None = None
    document_id: str | None = None
    transaction_date: date | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    currency: str | None = None
    unit_price: Decimal | None = None
    signed_value: Decimal | None = None
    validation_status: ValidationStatus = "valid"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    raw_values: dict[str, Any] = Field(default_factory=dict)


class ReviewItem(BaseModel):
    """Structured record requiring human review for ambiguous or missing data."""

    model_config = ConfigDict(extra="forbid")

    source_version_id: str
    source_row_number: int
    sheet_name: str | None = None
    field_name: str
    raw_value: Any = None
    proposed_value: Any = None
    reason_code: str
    severity: Severity = "review"
    status: str = "open"


class IngestionResult(BaseModel):
    """Complete aggregated outcome of ingesting a source representation."""

    model_config = ConfigDict(extra="forbid")

    source_file_id: str
    source_version_id: str
    parser_name: str
    parser_version: str
    rules_version: str
    scope: ScopeResult
    total_rows: int
    records: list[CanonicalSourceRecord] = Field(default_factory=list)
    review_items: list[ReviewItem] = Field(default_factory=list)
    result_hash: str

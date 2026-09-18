"""Immutable contracts used by the reconciliation engine.

These contracts deliberately contain source evidence references rather than raw
source rows.  They can therefore be passed between pure functions and later
stored by a repository without changing the reconciliation rules.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ChangeType = Literal["added", "replaced", "removed_from_current", "preserved"]
IssueSeverity = Literal["error", "warning"]
RecordKind = Literal["line", "credit", "cancellation", "invoice_total", "unknown"]


@dataclass(frozen=True)
class EvidenceRef:
    version_id: str
    source_record_id: str | None = None
    source_row_number: int | None = None
    field: str | None = None


@dataclass(frozen=True)
class UpdateScope:
    market: str
    supplier_ids: tuple[str, ...]
    update_mode: str = "replacement"
    evidence: tuple[EvidenceRef, ...] = ()
    full_market: bool = False


@dataclass(frozen=True)
class ReconciliationRecord:
    """A normalized record consumed by reconciliation.

    ``record_key`` is the stable business identity, not a database row id.  The
    optional source fields allow identity construction from Phase Three output
    while keeping this layer independent of SQLAlchemy models.
    """

    record_id: str
    version_id: str
    market: str
    supplier_id: str | None
    product_id: str | None
    value: Decimal | str | int | None
    record_kind: RecordKind = "line"
    currency: str | None = None
    quantity: Decimal | str | int | None = None
    document_id: str | None = None
    source_line_id: str | None = None
    source_row_number: int | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    record_key: str | None = None
    validation_status: str = "valid"
    metadata: tuple[tuple[str, str], ...] = ()
    unit: str | None = None


@dataclass(frozen=True)
class MaterializedRecord:
    record: ReconciliationRecord
    lineage: Literal[
        "introduced_by_incoming",
        "preserved_from_previous",
        "replaced_previous_record",
        "derived_from_correction",
    ]
    prior_record_id: str | None = None


@dataclass(frozen=True)
class ReconciliationIssue:
    code: str
    message: str
    severity: IssueSeverity = "error"
    evidence: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class RecordChange:
    record_key: str
    change_type: ChangeType
    prior_record_id: str | None = None
    incoming_record_id: str | None = None
    old_value: Decimal | None = None
    new_value: Decimal | None = None
    reason_code: str = ""
    evidence: tuple[EvidenceRef, ...] = ()
    affects_recommendation: bool = True


@dataclass(frozen=True)
class Totals:
    total: Decimal
    by_currency: dict[str, Decimal]
    credits: Decimal
    cancellations: Decimal
    excluded_invoice_totals: Decimal
    included_record_count: int
    excluded_record_count: int


@dataclass(frozen=True)
class ReconciliationSnapshot:
    previous_version_id: str
    incoming_version_id: str
    current_version_id: str | None
    scope: UpdateScope
    previous_records: tuple[ReconciliationRecord, ...]
    incoming_records: tuple[ReconciliationRecord, ...]
    current_records: tuple[MaterializedRecord, ...] = ()


@dataclass(frozen=True)
class ChangeSet:
    previous_version_id: str
    incoming_version_id: str
    current_version_id: str | None
    scope: UpdateScope
    added: tuple[RecordChange, ...] = ()
    replaced: tuple[RecordChange, ...] = ()
    removed_from_current: tuple[RecordChange, ...] = ()
    preserved: tuple[RecordChange, ...] = ()
    conflicts: tuple[ReconciliationIssue, ...] = ()
    warnings: tuple[ReconciliationIssue, ...] = ()
    result_hash: str = ""
    status: Literal["accepted", "needs_review", "rejected"] = "accepted"

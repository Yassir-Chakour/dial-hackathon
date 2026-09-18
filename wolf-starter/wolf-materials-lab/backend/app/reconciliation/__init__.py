"""Pure domain functions for Phase Four version reconciliation."""

from app.reconciliation.apply import apply_replacement
from app.reconciliation.contracts import (
    ChangeSet,
    MaterializedRecord,
    ReconciliationIssue,
    ReconciliationRecord,
    ReconciliationSnapshot,
    UpdateScope,
)
from app.reconciliation.identity import build_record_identity, match_records
from app.reconciliation.totals import calculate_signed_totals, reconcile_totals
from app.reconciliation.service import ReconciliationOutcome, ReconciliationService
from app.reconciliation.adapters import from_ingestion_record, from_persisted_record

__all__ = [
    "ChangeSet",
    "MaterializedRecord",
    "ReconciliationIssue",
    "ReconciliationRecord",
    "ReconciliationSnapshot",
    "UpdateScope",
    "apply_replacement",
    "build_record_identity",
    "calculate_signed_totals",
    "match_records",
    "reconcile_totals",
    "ReconciliationOutcome",
    "ReconciliationService",
    "from_ingestion_record",
    "from_persisted_record",
]

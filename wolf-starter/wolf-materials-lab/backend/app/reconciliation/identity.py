"""Deterministic business identity and matching rules."""

from dataclasses import dataclass
import hashlib
import json

from app.reconciliation.contracts import ReconciliationIssue, ReconciliationRecord


IDENTITY_STRATEGY_VERSION = "france-v1"


class IdentityConflictError(ValueError):
    """Raised when one version contains ambiguous duplicate business identity."""


def build_record_identity(record: ReconciliationRecord) -> str:
    """Build a stable identity without matching on descriptions, amounts or row order."""
    if record.record_key:
        return record.record_key
    if record.source_line_id:
        parts: tuple[str, ...] = (record.market, record.supplier_id or "", record.source_line_id)
    elif record.document_id and record.product_id and record.supplier_id:
        parts = (record.market, record.supplier_id, record.product_id, record.document_id)
    elif record.source_row_number is not None:
        # This is intentionally source-contextual: it cannot merge rows from
        # different versions, and it remains reviewable when no source ID exists.
        parts = (record.market, record.supplier_id or "", record.version_id, f"row:{record.source_row_number}")
    else:
        raise IdentityConflictError(f"Record {record.record_id} has no deterministic identity evidence.")
    return "|".join(parts)


@dataclass(frozen=True)
class MatchResult:
    matched: tuple[tuple[ReconciliationRecord, ReconciliationRecord], ...]
    incoming_only: tuple[ReconciliationRecord, ...]
    previous_only: tuple[ReconciliationRecord, ...]
    issues: tuple[ReconciliationIssue, ...] = ()


def match_records(
    previous: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    incoming: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
) -> MatchResult:
    previous_by_key: dict[str, ReconciliationRecord] = {}
    incoming_by_key: dict[str, ReconciliationRecord] = {}
    issues: list[ReconciliationIssue] = []

    for record in previous:
        key = build_record_identity(record)
        if key in previous_by_key:
            issues.append(ReconciliationIssue("identity_conflict", f"Duplicate prior identity: {key}"))
        previous_by_key[key] = record
    for record in incoming:
        key = build_record_identity(record)
        if key in incoming_by_key:
            issues.append(ReconciliationIssue("identity_conflict", f"Duplicate incoming identity: {key}"))
        incoming_by_key[key] = record

    matched = tuple((previous_by_key[key], incoming_by_key[key]) for key in sorted(previous_by_key.keys() & incoming_by_key.keys()))
    incoming_only = tuple(incoming_by_key[key] for key in sorted(incoming_by_key.keys() - previous_by_key.keys()))
    previous_only = tuple(previous_by_key[key] for key in sorted(previous_by_key.keys() - incoming_by_key.keys()))
    return MatchResult(matched, incoming_only, previous_only, tuple(issues))


def canonical_record_payload(record: ReconciliationRecord) -> dict[str, object]:
    return {
        "key": build_record_identity(record),
        "record_id": record.record_id,
        "version_id": record.version_id,
        "market": record.market,
        "supplier_id": record.supplier_id,
        "product_id": record.product_id,
        "value": str(record.value) if record.value is not None else None,
        "kind": record.record_kind,
        "currency": record.currency,
        "quantity": str(record.quantity) if record.quantity is not None else None,
        "document_id": record.document_id,
        "evidence": [ref.__dict__ for ref in record.evidence],
    }


def compute_reconciliation_hash(snapshot_payload: dict[str, object]) -> str:
    encoded = json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()

"""Reconciliation tools bridging workflow nodes with Phase Four reconciliation services."""

from decimal import Decimal
from typing import Any
from sqlalchemy.orm import Session

from app.db.models import SourceRecord
from app.persistence import SourceRepository
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord
from app.reconciliation.service import ReconciliationService
from app.workflows.tools.contracts import ReconcileInput, ReconcileOutput


def _to_reconciliation_record(r: SourceRecord) -> ReconciliationRecord:
    val = Decimal(r.value) if r.value is not None else None
    qty = Decimal(r.quantity) if r.quantity is not None else None
    raw = r.raw_values_json or {}
    market = r.source_version.market if r.source_version else "FR"
    return ReconciliationRecord(
        record_id=r.id,
        version_id=r.source_version_id,
        market=market,
        supplier_id=r.supplier,
        product_id=r.product,
        value=val,
        record_kind=r.record_kind if r.record_kind in ("line", "credit", "cancellation", "invoice_total") else "unknown",  # type: ignore[arg-type]
        currency=r.currency,
        quantity=qty,
        document_id=str(raw.get("Invoice") or raw.get("invoice_id") or raw.get("doc_id") or ""),
        source_line_id=str(raw.get("Item") or raw.get("item_id") or ""),
        source_row_number=r.source_row_number,
        evidence=(EvidenceRef(r.source_version_id, r.id, r.source_row_number),),
        record_key=r.record_key,
    )


def reconcile_tool(session: Session, payload: ReconcileInput) -> ReconcileOutput:
    """Executes deterministic supplier-subset reconciliation between two versions."""
    source_repo = SourceRepository()
    prev_rows = source_repo.get_records_for_version(session, payload.previous_version_id)
    inc_rows = source_repo.get_records_for_version(session, payload.incoming_version_id)

    previous_records = [_to_reconciliation_record(r) for r in prev_rows]
    incoming_records = [_to_reconciliation_record(r) for r in inc_rows]

    service = ReconciliationService()
    outcome = service.reconcile(
        session,
        event_key=payload.event_key,
        payload={"incoming": payload.incoming_version_id, "scope": payload.scope.supplier_ids},
        previous_version_id=payload.previous_version_id,
        incoming_version_id=payload.incoming_version_id,
        scope=payload.scope,
        previous_records=previous_records,
        incoming_records=incoming_records,
        tenant_id=payload.tenant_id,
    )

    run = outcome.run
    totals_data: dict[str, Any] = run.totals_json if run else {}
    changes_data: dict[str, Any] = run.changes_json if run else {}
    issue_dicts = [
        {"code": issue.code, "message": issue.message, "severity": issue.severity}
        for issue in outcome.issues
    ]

    return ReconcileOutput(
        reconciliation_run_id=run.id if run else "failed-run",
        status=outcome.status,  # type: ignore[arg-type]
        result_hash=outcome.result_hash or "",
        totals=totals_data,
        change_set=changes_data,
        issues=issue_dicts,
        replayed=outcome.event_replayed,
    )

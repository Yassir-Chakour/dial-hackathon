"""Adapters from Phase Three canonical records to Phase Four contracts."""

from typing import cast

from app.ingestion.contracts import CanonicalSourceRecord
from app.db.models import SourceRecord
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord, RecordKind


def from_ingestion_record(record: CanonicalSourceRecord, *, record_id: str | None = None) -> ReconciliationRecord:
    """Convert validated ingestion output without re-parsing or losing evidence."""
    evidence = tuple(
        EvidenceRef(
            version_id=ref.source_version_id,
            source_record_id=record_id,
            source_row_number=ref.source_row_number,
            field=ref.field_name,
        )
        for ref in record.evidence
    )
    kind = record.record_kind if record.record_kind in {"line", "credit", "cancellation", "invoice_total", "unknown"} else "unknown"
    return ReconciliationRecord(
        record_id=record_id or record.source_record_key,
        version_id=record.source_version_id,
        market="FR",
        supplier_id=record.supplier_id,
        product_id=record.product_id,
        value=record.signed_value,
        record_kind=cast(RecordKind, kind),
        currency=record.currency,
        quantity=record.quantity,
        document_id=record.document_id,
        source_line_id=record.source_record_key,
        source_row_number=record.source_row_number,
        evidence=evidence,
        record_key=record.source_record_key,
        validation_status=record.validation_status,
        unit=record.unit,
    )


def from_persisted_record(record: SourceRecord) -> ReconciliationRecord:
    """Convert a Phase Two row while retaining its source row as evidence."""
    kind = record.record_kind if record.record_kind in {"line", "credit", "cancellation", "invoice_total", "unknown"} else "unknown"
    return ReconciliationRecord(
        record_id=record.id,
        version_id=record.source_version_id,
        market=str(record.raw_values_json.get("market", "FR")),
        supplier_id=record.supplier,
        product_id=record.product,
        value=record.value,
        record_kind=cast(RecordKind, kind),
        currency=record.currency,
        quantity=record.quantity,
        source_line_id=record.record_key,
        source_row_number=record.source_row_number,
        evidence=(EvidenceRef(record.source_version_id, record.id, record.source_row_number),),
        record_key=record.record_key,
        validation_status=record.validation_status,
        unit=record.unit,
    )

"""Ingestion pipeline orchestrating reading, classification, normalization, and hashing."""

from typing import Any

from app.ingestion.classifier import classify_row
from app.ingestion.contracts import (
    CanonicalSourceRecord,
    IngestionResult,
    ReviewItem,
    ScopeResult,
    SourceRow,
)
from app.ingestion.evidence import compute_ingestion_result_hash
from app.ingestion.france_rules import (
    COL_INVOICE_NUM_1,
    COL_ITEM_1,
    FRANCE_RULES_VERSION,
    extract_france_scope,
    map_france_row,
)
from app.ingestion.headers import detect_header_context
from app.ingestion.validators import (
    build_source_record_key,
    validate_canonical_record,
)

PARSER_NAME = "france-fixture-ingestion-pipeline"
PARSER_VERSION = "1.0.0"


class IngestionPipeline:
    """Orchestrates ingestion stages deterministically."""

    def __init__(
        self,
        parser_name: str = PARSER_NAME,
        parser_version: str = PARSER_VERSION,
        rules_version: str = FRANCE_RULES_VERSION,
    ) -> None:
        self.parser_name = parser_name
        self.parser_version = parser_version
        self.rules_version = rules_version

    def process(
        self,
        raw_rows: list[SourceRow],
        source_file_id: str,
        source_version_id: str,
    ) -> IngestionResult:
        """Run the ingestion pipeline on extracted SourceRow items."""
        header_context, data_rows = detect_header_context(raw_rows)

        scope: ScopeResult = extract_france_scope(data_rows)

        records: list[CanonicalSourceRecord] = []
        all_review_items: list[ReviewItem] = []

        for row in data_rows:
            record_kind, _ = classify_row(row, header_context)

            doc_id = None
            item_id = None
            if len(row.cells) > COL_INVOICE_NUM_1 and row.cells[COL_INVOICE_NUM_1] is not None:
                doc_id = str(row.cells[COL_INVOICE_NUM_1]).strip()
            if len(row.cells) > COL_ITEM_1 and row.cells[COL_ITEM_1] is not None:
                item_id = str(row.cells[COL_ITEM_1]).strip()

            record_key = build_source_record_key(
                source_version_id=source_version_id,
                row_number=row.row_number,
                doc_id=doc_id,
                item_id=item_id,
            )

            record = map_france_row(
                row=row,
                record_kind=record_kind,
                source_record_key=record_key,
            )

            validated_record, review_items = validate_canonical_record(record)
            records.append(validated_record)
            all_review_items.extend(review_items)

        # Build deterministic payload for hashing (excluding timestamps and IDs)
        hashable_payload: dict[str, Any] = {
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "rules_version": self.rules_version,
            "scope": {
                "market": scope.market,
                "update_mode": scope.update_mode,
                "supplier_scope": scope.supplier_scope,
            },
            "records": [
                {
                    "key": r.source_record_key,
                    "kind": r.record_kind,
                    "supplier_id": r.supplier_id,
                    "product_id": r.product_id,
                    "quantity": str(r.quantity) if r.quantity is not None else None,
                    "unit": r.unit,
                    "signed_value": str(r.signed_value) if r.signed_value is not None else None,
                    "currency": r.currency,
                    "date": str(r.transaction_date) if r.transaction_date is not None else None,
                    "status": r.validation_status,
                }
                for r in records
            ],
            "review_count": len(all_review_items),
        }

        result_hash = compute_ingestion_result_hash(hashable_payload)

        return IngestionResult(
            source_file_id=source_file_id,
            source_version_id=source_version_id,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            rules_version=self.rules_version,
            scope=scope,
            total_rows=len(raw_rows),
            records=records,
            review_items=all_review_items,
            result_hash=result_hash,
        )

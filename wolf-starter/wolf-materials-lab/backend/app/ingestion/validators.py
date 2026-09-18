"""Record validation and human-review routing logic."""

from decimal import Decimal

from app.ingestion.contracts import CanonicalSourceRecord, ReviewItem, ValidationStatus


def build_source_record_key(
    source_version_id: str,
    row_number: int,
    doc_id: str | None = None,
    item_id: str | None = None,
) -> str:
    """Construct a deterministic unique key for a source record within a version."""
    doc_part = f":doc-{doc_id}" if doc_id else ""
    item_part = f":item-{item_id}" if item_id else ""
    return f"{source_version_id}:row-{row_number}{doc_part}{item_part}"


def validate_canonical_record(
    record: CanonicalSourceRecord,
) -> tuple[CanonicalSourceRecord, list[ReviewItem]]:
    """Validate a canonical source record against business invariants.

    Returns the updated record and any generated ReviewItem instances.
    """
    review_items: list[ReviewItem] = []
    errors = list(record.errors)
    warnings = list(record.warnings)

    # If it's a header, blank, or note, validation rules are minimal
    if record.record_kind in ("header", "blank", "note"):
        record.validation_status = "valid"
        return record, []

    # 1. Validate required business fields for line items and cancellations
    if record.record_kind in ("line", "credit", "cancellation"):
        if not record.product_id:
            errors.append("Product code is missing.")
            review_items.append(
                ReviewItem(
                    source_version_id=record.source_version_id,
                    source_row_number=record.source_row_number,
                    sheet_name=record.sheet_name,
                    field_name="product_id",
                    raw_value=record.raw_values.get("Article"),
                    reason_code="missing_product_code",
                    severity="error",
                )
            )

        if not record.supplier_id:
            warnings.append("Supplier could not be resolved from article.")
            review_items.append(
                ReviewItem(
                    source_version_id=record.source_version_id,
                    source_row_number=record.source_row_number,
                    sheet_name=record.sheet_name,
                    field_name="supplier_id",
                    raw_value=record.raw_values.get("Article"),
                    reason_code="unmapped_supplier",
                    severity="review",
                )
            )

        if record.quantity is None:
            errors.append("Quantity is missing or invalid.")
            review_items.append(
                ReviewItem(
                    source_version_id=record.source_version_id,
                    source_row_number=record.source_row_number,
                    sheet_name=record.sheet_name,
                    field_name="quantity",
                    raw_value=record.raw_values.get("Invoiced quantity"),
                    reason_code="invalid_quantity",
                    severity="error",
                )
            )

        if record.signed_value is None:
            errors.append("Net value is missing or invalid.")
            review_items.append(
                ReviewItem(
                    source_version_id=record.source_version_id,
                    source_row_number=record.source_row_number,
                    sheet_name=record.sheet_name,
                    field_name="signed_value",
                    raw_value=record.raw_values.get("Net value"),
                    reason_code="invalid_net_value",
                    severity="error",
                )
            )

        if not record.currency:
            errors.append("Currency code is missing.")
            review_items.append(
                ReviewItem(
                    source_version_id=record.source_version_id,
                    source_row_number=record.source_row_number,
                    sheet_name=record.sheet_name,
                    field_name="currency",
                    raw_value=record.raw_values.get("Currency"),
                    reason_code="missing_currency",
                    severity="error",
                )
            )

        if not record.transaction_date:
            errors.append("Transaction date is missing or invalid.")
            review_items.append(
                ReviewItem(
                    source_version_id=record.source_version_id,
                    source_row_number=record.source_row_number,
                    sheet_name=record.sheet_name,
                    field_name="transaction_date",
                    raw_value=record.raw_values.get("Invoice date"),
                    reason_code="invalid_date",
                    severity="error",
                )
            )

        # 2. Validate sign consistency for credit notes and cancellations
        if record.record_kind in ("credit", "cancellation"):
            if record.signed_value is not None and record.signed_value > Decimal("0"):
                warnings.append("Credit note has positive net value; expected negative.")
                review_items.append(
                    ReviewItem(
                        source_version_id=record.source_version_id,
                        source_row_number=record.source_row_number,
                        sheet_name=record.sheet_name,
                        field_name="signed_value",
                        raw_value=str(record.signed_value),
                        reason_code="unexpected_positive_credit_value",
                        severity="review",
                    )
                )

    # Determine overall status
    val_status: ValidationStatus = "valid"
    if errors:
        val_status = "invalid"
    elif review_items:
        val_status = "needs_review"

    record.errors = errors
    record.warnings = warnings
    record.validation_status = val_status

    return record, review_items

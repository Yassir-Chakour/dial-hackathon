"""Tests for business validation and review item routing."""

from datetime import date
from decimal import Decimal

from app.ingestion.contracts import CanonicalSourceRecord
from app.ingestion.validators import validate_canonical_record


def test_validation_valid_line() -> None:
    """Test fully valid canonical line passes validation without review items."""
    record = CanonicalSourceRecord(
        source_record_key="rec-1",
        source_version_id="ver-1",
        source_row_number=2,
        record_kind="line",
        supplier_id="sup-aster",
        supplier_label="3M",
        product_id="WLF-1008",
        product_label="Paint cup",
        document_id="FAC-0001",
        transaction_date=date(2026, 9, 4),
        quantity=Decimal("100"),
        unit="piece",
        currency="EUR",
        unit_price=Decimal("10.00"),
        signed_value=Decimal("1000.00"),
    )

    validated, review_items = validate_canonical_record(record)
    assert validated.validation_status == "valid"
    assert len(review_items) == 0
    assert len(validated.errors) == 0


def test_validation_missing_fields_routes_to_review() -> None:
    """Test missing required fields generates error ReviewItems."""
    record = CanonicalSourceRecord(
        source_record_key="rec-2",
        source_version_id="ver-1",
        source_row_number=3,
        record_kind="line",
        supplier_id=None,
        product_id=None,  # missing
        quantity=None,  # missing
        signed_value=None,  # missing
    )

    validated, review_items = validate_canonical_record(record)
    assert validated.validation_status == "invalid"
    assert len(review_items) >= 3
    reason_codes = [item.reason_code for item in review_items]
    assert "missing_product_code" in reason_codes
    assert "invalid_quantity" in reason_codes
    assert "invalid_net_value" in reason_codes


def test_validation_credit_with_positive_amount() -> None:
    """Test credit note with positive amount generates a review warning item."""
    record = CanonicalSourceRecord(
        source_record_key="rec-3",
        source_version_id="ver-1",
        source_row_number=4,
        record_kind="credit",
        supplier_id="sup-aster",
        product_id="WLF-1008",
        transaction_date=date(2026, 9, 4),
        quantity=Decimal("-10"),
        unit="piece",
        currency="EUR",
        signed_value=Decimal("500.00"),  # Unexpected positive value on credit
    )

    validated, review_items = validate_canonical_record(record)
    assert validated.validation_status == "needs_review"
    assert any(item.reason_code == "unexpected_positive_credit_value" for item in review_items)

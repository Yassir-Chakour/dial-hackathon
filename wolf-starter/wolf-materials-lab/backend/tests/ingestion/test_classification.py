"""Tests for row kind classification: line, credit, cancellation, totals, headers, blanks."""

from app.ingestion.classifier import classify_row
from app.ingestion.contracts import HeaderContext, SourceRow


def test_classify_standard_line() -> None:
    """Test standard commercial line classification."""
    context = HeaderContext(raw_labels=["Site", "Invoice", "Article", "Quantity", "Net value"])
    row = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=2,
        cells=["SITE-001", "FAC-WOLF-0001", "WLF-1008", "174", "8727.84"],
    )
    kind, meta = classify_row(row, context)
    assert kind == "line"
    assert meta["calculation_role"] == "included_in_line_sum"


def test_classify_cancellation_and_credit_note() -> None:
    """Test credit note and cancellation rows with negative values."""
    context = HeaderContext(raw_labels=["Invoice", "Article", "Quantity", "Net value", "Type"])
    row_cancel = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=2,
        cells=["FAC-0001", "WLF-1008", "-226", "-11336.16", "Invoice cancellation"],
    )
    kind, meta = classify_row(row_cancel, context)
    assert kind == "cancellation"
    assert meta["calculation_role"] == "signed_line_item"

    row_credit = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=3,
        cells=["FAC-0002", "WLF-1018", "-297", "-13549.14", "Credit note"],
    )
    kind, meta = classify_row(row_credit, context)
    assert kind == "credit"
    assert meta["calculation_role"] == "signed_line_item"


def test_classify_repeated_invoice_total() -> None:
    """Test standalone document total rows are excluded from line sum calculations."""
    context = HeaderContext(raw_labels=["Invoice", "Description", "Total"])
    row = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=10,
        cells=["FAC-0001", "Invoice total", "953.04"],
    )
    kind, meta = classify_row(row, context)
    assert kind == "invoice_total"
    assert meta["calculation_role"] == "excluded_from_line_sum"


def test_classify_repeated_header_and_blank() -> None:
    """Test repeated header row in the middle of a file and blank rows."""
    context = HeaderContext(raw_labels=["Site code", "Invoice", "Article", "Net value"])

    # Repeated header
    row_header = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=20,
        cells=["Site code", "Invoice", "Article", "Net value"],
    )
    kind, meta = classify_row(row_header, context)
    assert kind == "header"
    assert meta["calculation_role"] == "excluded_from_line_sum"

    # Blank row
    row_blank = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=21,
        cells=["", None, "   ", ""],
    )
    kind, _ = classify_row(row_blank, context)
    assert kind == "blank"

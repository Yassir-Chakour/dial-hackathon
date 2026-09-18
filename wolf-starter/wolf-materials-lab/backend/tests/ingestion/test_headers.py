"""Tests for header detection and duplicate-column tracking."""

from app.ingestion.contracts import SourceRow
from app.ingestion.headers import detect_header_context, normalize_header


def test_normalize_header() -> None:
    """Test header string cleaning and normalization."""
    assert normalize_header(" Site Code ") == "site code"
    assert normalize_header("Invoice-Date (FR)") == "invoice date fr"
    assert normalize_header("Net_Value#") == "net value"


def test_detect_header_with_duplicate_labels() -> None:
    """Test detecting headers with duplicate column names and mapping positions."""
    rows = [
        SourceRow(
            source_file_id="f1",
            source_version_id="v1",
            row_number=1,
            cells=["Site", "Invoice", "Currency", "Item", "Net Value", "Currency", "Item"],
        ),
        SourceRow(
            source_file_id="f1",
            source_version_id="v1",
            row_number=2,
            cells=["S1", "INV-1", "EUR", "10", "100.00", "EUR", "1"],
        ),
    ]

    context, data_rows = detect_header_context(rows)
    assert context.selected_row == 1
    assert context.confidence == "high"
    assert "currency" in context.duplicate_labels
    assert "item" in context.duplicate_labels
    assert context.label_to_indices["currency"] == [2, 5]
    assert context.label_to_indices["item"] == [3, 6]
    assert len(data_rows) == 1
    assert data_rows[0].row_number == 2


def test_detect_header_preamble_rows() -> None:
    """Test header detection when preamble or empty rows precede the table header."""
    rows = [
        SourceRow(source_file_id="f1", source_version_id="v1", row_number=1, cells=["Report Title", ""]),
        SourceRow(source_file_id="f1", source_version_id="v1", row_number=2, cells=["Export Date: 2026-09-01", ""]),
        SourceRow(
            source_file_id="f1",
            source_version_id="v1",
            row_number=3,
            cells=["Site code", "Invoice", "Article", "Invoiced quantity", "Net value"],
        ),
        SourceRow(source_file_id="f1", source_version_id="v1", row_number=4, cells=["S1", "FAC-1", "WLF-1008", "10", "100"]),
    ]

    context, data_rows = detect_header_context(rows)
    assert context.selected_row == 3
    assert len(data_rows) == 1
    assert data_rows[0].row_number == 4

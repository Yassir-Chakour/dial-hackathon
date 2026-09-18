"""Tests for safe CSV and raw matrix readers."""

import pytest

from app.ingestion.csv_reader import CsvReaderError, read_csv_rows
from app.ingestion.matrix_reader import MatrixReaderError, read_matrix_rows


def test_csv_reader_basic_and_row_preservation() -> None:
    """Test reading basic CSV rows preserves 1-based row numbers and raw values."""
    csv_text = "Header A,Header B,Header C\nval1,val2,val3\nval4,,val6\n"
    rows = read_csv_rows(csv_text, source_file_id="f1", source_version_id="v1")
    assert len(rows) == 3
    assert rows[0].row_number == 1
    assert rows[0].cells == ["Header A", "Header B", "Header C"]
    assert rows[1].row_number == 2
    assert rows[1].cells == ["val1", "val2", "val3"]
    assert rows[2].row_number == 3
    assert rows[2].cells == ["val4", "", "val6"]


def test_csv_reader_bom_and_quoted_newlines() -> None:
    """Test reading UTF-8 with BOM and embedded newlines in quoted fields."""
    bom_content = "\ufeffCol1,Col2\n\"Line 1\nLine 2\",val".encode("utf-8")
    rows = read_csv_rows(bom_content, source_file_id="f1", source_version_id="v1")
    assert len(rows) == 2
    assert rows[0].cells == ["Col1", "Col2"]
    assert rows[1].cells == ["Line 1\nLine 2", "val"]


def test_csv_reader_formula_safety() -> None:
    """Test cells with formula prefixes (=, +, -, @) are kept as plain data."""
    csv_content = "Name,Formula\nItem 1,=SUM(A1:A10)\nItem 2,+CMD\nItem 3,@HYPERLINK\n"
    rows = read_csv_rows(csv_content, source_file_id="f1", source_version_id="v1")
    assert rows[1].cells[1] == "=SUM(A1:A10)"
    assert rows[2].cells[1] == "+CMD"
    assert rows[3].cells[1] == "@HYPERLINK"


def test_csv_reader_max_bytes_and_rows_enforcement() -> None:
    """Test exceeding byte limit or row limit raises CsvReaderError."""
    large_bytes = b"A,B\n" * 100
    with pytest.raises(CsvReaderError, match="exceeds maximum limit"):
        read_csv_rows(large_bytes, source_file_id="f1", source_version_id="v1", max_bytes=50)

    with pytest.raises(CsvReaderError, match="row count exceeds"):
        read_csv_rows("A,B\n1,2\n3,4\n5,6\n", source_file_id="f1", source_version_id="v1", max_rows=2)


def test_matrix_reader_basic_and_nested_rejection() -> None:
    """Test matrix reader processes 2D lists and rejects nested objects."""
    matrix = [
        ["Col1", "Col2"],
        ["Val1", 100],
        ["Val2", None],
    ]
    rows = read_matrix_rows(matrix, source_file_id="f1", source_version_id="v1")
    assert len(rows) == 3
    assert rows[0].cells == ["Col1", "Col2"]
    assert rows[1].cells == ["Val1", 100]
    assert rows[2].cells == ["Val2", None]

    # Rejection of nested dict in cell
    invalid_matrix = [
        ["Col1", {"nested": "dict"}],
    ]
    with pytest.raises(MatrixReaderError, match="Unsupported nested value"):
        read_matrix_rows(invalid_matrix, source_file_id="f1", source_version_id="v1")

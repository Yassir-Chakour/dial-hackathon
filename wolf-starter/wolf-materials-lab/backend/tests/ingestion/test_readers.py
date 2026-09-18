"""Tests for safe CSV and raw matrix readers."""

import pytest
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.ingestion.csv_reader import CsvReaderError, read_csv_rows
from app.ingestion.matrix_reader import MatrixReaderError, read_matrix_rows
from app.ingestion.xlsx_reader import XlsxReaderError, read_xlsx_rows


def _xlsx_bytes(sheet_xml: str, *, shared_strings: str | None = None) -> bytes:
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets><sheet name="Orders" sheetId="1" r:id="rId1"/></sheets>
    </workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    </Relationships>"""
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        if shared_strings is not None:
            archive.writestr("xl/sharedStrings.xml", shared_strings)
    return output.getvalue()


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


def test_xlsx_reader_preserves_sheets_positions_and_values() -> None:
    content = _xlsx_bytes("""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>Product</t></is></c><c r="C1" t="inlineStr"><is><t>Value</t></is></c></row>
        <row r="3"><c r="B3" t="s"><v>0</v></c><c r="C3"><v>12.50</v></c></row>
      </sheetData>
    </worksheet>""", shared_strings="""<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Item A</t></si></sst>""")
    rows = read_xlsx_rows(content, source_file_id="f1", source_version_id="v1")
    assert [(row.sheet_name, row.row_number, row.cells) for row in rows] == [
        ("Orders", 1, ["Product", "", "Value"]),
        ("Orders", 3, ["", "Item A", "12.50"]),
    ]
    assert rows[1].metadata["workbook_part"] == "xl/worksheets/sheet1.xml"


def test_xlsx_reader_rejects_formulas_and_limits() -> None:
    formula = _xlsx_bytes("""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1"><c r="A1"><f>SUM(1,2)</f><v>3</v></c></row></sheetData>
    </worksheet>""")
    with pytest.raises(XlsxReaderError, match="Formula cells are unsupported"):
        read_xlsx_rows(formula, source_file_id="f1", source_version_id="v1")

    with pytest.raises(XlsxReaderError, match="maximum limit"):
        read_xlsx_rows(formula, source_file_id="f1", source_version_id="v1", max_bytes=10)

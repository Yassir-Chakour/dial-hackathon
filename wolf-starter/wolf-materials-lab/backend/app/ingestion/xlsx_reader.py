"""Bounded, non-executing XLSX reader.

The reader intentionally uses the XLSX package format directly instead of a
spreadsheet application.  It extracts stored cell values into the same
``SourceRow`` contract as the CSV and matrix readers and never evaluates
formulas, macros, links, or embedded objects.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

from app.ingestion.contracts import SourceRow

DEFAULT_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_SHEETS = 32
DEFAULT_MAX_ROWS = 100_000
DEFAULT_MAX_COLS = 200
DEFAULT_MAX_ZIP_ENTRIES = 512

_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_FORBIDDEN_PARTS = ("/vbaProject.bin", "/externalLinks/", "/embeddings/")


class XlsxReaderError(Exception):
    """Raised when an XLSX is unsupported, malformed, or exceeds a bound."""


def _column_number(reference: str) -> int:
    match = _CELL_REF.match(reference.upper())
    if not match:
        raise XlsxReaderError(f"Invalid XLSX cell reference '{reference}'.")
    number = 0
    for char in match.group(1):
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number


def _xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError as exc:
        raise XlsxReaderError(f"XLSX is missing required part '{name}'.") from exc
    except ET.ParseError as exc:
        raise XlsxReaderError(f"XLSX part '{name}' is malformed.") from exc


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = _xml(zf, "xl/sharedStrings.xml")
    return ["".join(node.itertext()) for node in root.findall("main:si", _NS)]


def _workbook_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    root = _xml(zf, "xl/workbook.xml")
    rel_root = _xml(zf, "xl/_rels/workbook.xml.rels")
    relationships = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rel_root.findall("pkgrel:Relationship", _NS)
        if rel.attrib.get("Type", "").endswith("/worksheet")
    }
    sheets: list[tuple[str, str]] = []
    for sheet in root.findall("main:sheets/main:sheet", _NS):
        rel_id = sheet.attrib.get(f"{{{_NS['rel']}}}id")
        target = relationships.get(rel_id or "")
        if not target:
            raise XlsxReaderError("XLSX worksheet relationship is missing.")
        target = posixpath.normpath(posixpath.join("xl", target))
        if not target.startswith("xl/") or target not in zf.namelist():
            raise XlsxReaderError("XLSX worksheet relationship points outside the package.")
        sheets.append((sheet.attrib.get("name", ""), target))
    return sheets


def _cell_value(cell: ET.Element, shared: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("main:v", _NS)
    inline_node = cell.find("main:is", _NS)
    if cell.find("main:f", _NS) is not None:
        raise XlsxReaderError("Formula cells are unsupported; provide stored values only.")
    if cell_type == "inlineStr":
        return "".join(inline_node.itertext()) if inline_node is not None else ""
    if value_node is None:
        return ""
    raw = value_node.text or ""
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError) as exc:
            raise XlsxReaderError("XLSX shared-string index is invalid.") from exc
    if cell_type == "b":
        return raw == "1"
    if cell_type == "e":
        return raw
    # Keep numeric/date serials as source values. Normalization owns locale and
    # date semantics, and this avoids silently changing financial data.
    return raw


def read_xlsx_rows(
    content: bytes,
    source_file_id: str,
    source_version_id: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_decompressed_bytes: int = DEFAULT_MAX_DECOMPRESSED_BYTES,
    max_zip_entries: int = DEFAULT_MAX_ZIP_ENTRIES,
    max_sheets: int = DEFAULT_MAX_SHEETS,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_cols: int = DEFAULT_MAX_COLS,
) -> list[SourceRow]:
    """Extract bounded worksheet rows without evaluating workbook behavior."""
    if len(content) > max_bytes:
        raise XlsxReaderError(f"XLSX content size ({len(content)} bytes) exceeds maximum limit of {max_bytes} bytes.")
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise XlsxReaderError("XLSX is not a valid ZIP package.") from exc

    with zf:
        names = zf.namelist()
        if len(names) > max_zip_entries:
            raise XlsxReaderError(f"XLSX contains too many ZIP entries (maximum {max_zip_entries}).")
        total_uncompressed = sum(info.file_size for info in zf.infolist())
        if total_uncompressed > max_decompressed_bytes:
            raise XlsxReaderError("XLSX decompressed size exceeds the maximum limit.")
        for name in names:
            normalized = "/" + posixpath.normpath(name)
            if name.startswith("/") or ".." in normalized.split("/") or "\\" in name:
                raise XlsxReaderError("XLSX contains an unsafe package path.")
            if any(part in normalized for part in _FORBIDDEN_PARTS):
                raise XlsxReaderError("XLSX macros, external links, and embedded objects are unsupported.")

        try:
            sheets = _workbook_sheets(zf)
            shared = _shared_strings(zf)
        except (KeyError, ET.ParseError) as exc:
            raise XlsxReaderError("XLSX package metadata is malformed.") from exc
        if not sheets:
            raise XlsxReaderError("XLSX contains no worksheets.")
        if len(sheets) > max_sheets:
            raise XlsxReaderError(f"XLSX sheet count exceeds maximum allowed limit of {max_sheets}.")

        rows: list[SourceRow] = []
        for sheet_name, sheet_part in sheets:
            root = _xml(zf, sheet_part)
            sheet_data = root.find("main:sheetData", _NS)
            if sheet_data is None:
                continue
            for row_node in sheet_data.findall("main:row", _NS):
                row_number = int(row_node.attrib.get("r", str(len(rows) + 1)))
                if row_number > max_rows:
                    raise XlsxReaderError(f"Worksheet row count exceeds maximum allowed limit of {max_rows} rows.")
                cells: list[Any] = []
                for cell in row_node.findall("main:c", _NS):
                    reference = cell.attrib.get("r", "")
                    column = _column_number(reference)
                    if column > max_cols:
                        raise XlsxReaderError(f"Worksheet column count exceeds maximum allowed limit of {max_cols} columns.")
                    while len(cells) < column:
                        cells.append("")
                    cells[column - 1] = _cell_value(cell, shared)
                rows.append(SourceRow(
                    source_file_id=source_file_id,
                    source_version_id=source_version_id,
                    row_number=row_number,
                    sheet_name=sheet_name,
                    cells=cells,
                    raw_text=",".join(str(value) for value in cells),
                    metadata={"workbook_part": sheet_part},
                ))
    return rows

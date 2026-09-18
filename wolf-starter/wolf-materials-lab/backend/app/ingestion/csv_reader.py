"""Safe CSV reader preserving row positions, empty cells, and raw values."""

import csv
import io
from typing import Any

from app.ingestion.contracts import SourceRow

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_ROWS = 100_000
DEFAULT_MAX_COLS = 200


class CsvReaderError(Exception):
    """Raised when CSV reading fails due to size, encoding, or structure."""


def read_csv_rows(
    content: bytes | str,
    source_file_id: str,
    source_version_id: str,
    sheet_name: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_cols: int = DEFAULT_MAX_COLS,
) -> list[SourceRow]:
    """Read CSV payload safely into a sequence of SourceRow objects.

    Enforces size and row limits, supports UTF-8 with or without BOM,
    preserves 1-based row numbers, empty cells, and treats formula prefixes as data.
    """
    if isinstance(content, bytes):
        if len(content) > max_bytes:
            raise CsvReaderError(
                f"CSV content size ({len(content)} bytes) exceeds maximum limit of {max_bytes} bytes."
            )
        # Attempt UTF-8 with BOM awareness first
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as exc:
                raise CsvReaderError(f"Failed to decode CSV content: {exc}") from exc
    else:
        text = content
        if len(text.encode("utf-8")) > max_bytes:
            raise CsvReaderError(f"CSV text size exceeds maximum limit of {max_bytes} bytes.")

    reader = csv.reader(io.StringIO(text))
    rows: list[SourceRow] = []

    for row_idx, raw_cells in enumerate(reader, start=1):
        if row_idx > max_rows:
            raise CsvReaderError(f"CSV row count exceeds maximum allowed limit of {max_rows} rows.")

        if len(raw_cells) > max_cols:
            raise CsvReaderError(
                f"Row {row_idx} column count ({len(raw_cells)}) exceeds limit of {max_cols} columns."
            )

        # Sanitize cells: treat '=' / '+' / '-' / '@' as plain data, never executable
        cells: list[Any] = [str(c) if c is not None else "" for c in raw_cells]

        rows.append(
            SourceRow(
                source_file_id=source_file_id,
                source_version_id=source_version_id,
                row_number=row_idx,
                sheet_name=sheet_name,
                cells=cells,
                raw_text=",".join(str(c) for c in cells),
            )
        )

    return rows

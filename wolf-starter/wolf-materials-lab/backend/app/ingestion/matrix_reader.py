"""Raw matrix reader adapting list-of-lists representations into SourceRow sequences."""

from typing import Any

from app.ingestion.contracts import SourceRow

DEFAULT_MAX_ROWS = 100_000
DEFAULT_MAX_COLS = 200


class MatrixReaderError(Exception):
    """Raised when raw matrix input is malformed or exceeds bounds."""


def read_matrix_rows(
    matrix: list[list[Any]],
    source_file_id: str,
    source_version_id: str,
    sheet_name: str | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_cols: int = DEFAULT_MAX_COLS,
) -> list[SourceRow]:
    """Adapt a raw 2D matrix into a sequence of SourceRow objects.

    Rejects unsupported nested data structures (e.g., dicts or nested lists within cells).
    """
    if not isinstance(matrix, list):
        raise MatrixReaderError("Matrix input must be a list of rows.")

    if len(matrix) > max_rows:
        raise MatrixReaderError(f"Matrix exceeds maximum row limit of {max_rows} rows.")

    rows: list[SourceRow] = []
    for row_idx, raw_row in enumerate(matrix, start=1):
        if not isinstance(raw_row, (list, tuple)):
            raise MatrixReaderError(f"Row {row_idx} is not a valid list/tuple.")

        if len(raw_row) > max_cols:
            raise MatrixReaderError(
                f"Row {row_idx} column count ({len(raw_row)}) exceeds limit of {max_cols} columns."
            )

        sanitized_cells: list[Any] = []
        for col_idx, cell in enumerate(raw_row):
            if isinstance(cell, (dict, list, set)):
                raise MatrixReaderError(
                    f"Unsupported nested value at row {row_idx}, column {col_idx}: {type(cell).__name__} is not allowed."
                )
            sanitized_cells.append(cell)

        rows.append(
            SourceRow(
                source_file_id=source_file_id,
                source_version_id=source_version_id,
                row_number=row_idx,
                sheet_name=sheet_name,
                cells=sanitized_cells,
                raw_text=",".join(str(c) if c is not None else "" for c in sanitized_cells),
            )
        )

    return rows

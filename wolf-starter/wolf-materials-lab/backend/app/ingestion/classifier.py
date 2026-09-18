"""Deterministic row-kind classification using structural and value evidence."""

from typing import Any

from app.ingestion.contracts import HeaderContext, RecordKind, SourceRow


def is_row_blank(row: SourceRow) -> bool:
    """Check if all cells in a row are None or empty/whitespace strings."""
    return all(c is None or str(c).strip() == "" for c in row.cells)


def is_repeated_header(row: SourceRow, context: HeaderContext) -> bool:
    """Check if a row repeats the table headers."""
    if not context.raw_labels or len(row.cells) < len(context.raw_labels):
        return False
    row_strings = [str(c).strip().lower() for c in row.cells[: len(context.raw_labels)]]
    header_strings = [h.strip().lower() for h in context.raw_labels]
    matches = sum(1 for r, h in zip(row_strings, header_strings, strict=False) if r == h and r != "")
    return matches >= max(3, int(len(header_strings) * 0.7))


def classify_row(row: SourceRow, context: HeaderContext) -> tuple[RecordKind, dict[str, Any]]:
    """Classify a source row into a specific RecordKind with associated reason and metadata.

    Distinguishes regular line items, cancellations, credits, repeated invoice totals,
    repeated headers, notes, and blank rows.
    """
    # 1. Check blank
    if is_row_blank(row):
        return "blank", {"reason": "All cells are empty"}

    # 2. Check repeated header
    if is_repeated_header(row, context):
        return "header", {
            "reason": "Row repeats column header labels",
            "calculation_role": "excluded_from_line_sum",
        }

    row_text = " ".join(str(c).lower() for c in row.cells if c is not None)

    # 3. Check for cancellation / credit note indicators
    cancellation_indicators = [
        "credit_note",
        "credit note",
        "invoice cancellation",
        "cancellation",
        "storno",
        "gutschrift",
    ]
    is_cancellation = any(ind in row_text for ind in cancellation_indicators)

    # Check for negative amounts
    has_negative_number = False
    for cell in row.cells:
        if cell is not None:
            s = str(cell).strip()
            if s.startswith("-") and any(ch.isdigit() for ch in s):
                has_negative_number = True
                break

    if is_cancellation or has_negative_number:
        kind: RecordKind = "cancellation" if "cancellation" in row_text else "credit"
        return kind, {
            "reason": "Contains credit/cancellation document indicator or negative value",
            "calculation_role": "signed_line_item",
        }

    # 4. Check for invoice total / subtotal row (not a line item)
    total_indicators = ["total", "gesamt", "subtotal", "invoice total", "rechnungssumme"]
    is_standalone_total = any(
        str(c).strip().lower() in total_indicators for c in row.cells if c is not None
    )
    if is_standalone_total and not any("wlf-" in str(c).lower() for c in row.cells if c is not None):
        return "invoice_total", {
            "reason": "Standalone document total row",
            "calculation_role": "excluded_from_line_sum",
            "reason_code": "document_total_row",
        }

    # 5. Check if it's a regular commercial line item
    # Evidence: has article/product code or quantity + price
    has_article = any("wlf-" in str(c).lower() for c in row.cells if c is not None)
    has_invoice = any("fac-" in str(c).lower() for c in row.cells if c is not None)
    if has_article or has_invoice:
        return "line", {
            "reason": "Contains article and transaction document evidence",
            "calculation_role": "included_in_line_sum",
        }

    # 6. Check note
    non_empty = [str(c).strip() for c in row.cells if c is not None and str(c).strip()]
    if len(non_empty) <= 2 and not any(any(ch.isdigit() for ch in c) for c in non_empty):
        return "note", {"reason": "Non-commercial textual note"}

    return "unknown", {"reason": "Could not determine row kind with high confidence"}

"""Header detection, normalization, and duplicate-header tracking."""

import re
from typing import Any

from app.ingestion.contracts import Confidence, HeaderContext, SourceRow

KNOWN_HEADER_KEYWORDS = {
    "site",
    "invoice",
    "article",
    "description",
    "quantity",
    "net",
    "value",
    "currency",
    "item",
    "order",
    "payer",
    "document",
    "date",
    "total",
    "supplier",
    "product",
    "brand",
    "unit",
    "price",
}


def normalize_header(label: Any) -> str:
    """Normalize a header string for matching: lowercase, strip, and clean punctuation."""
    if label is None:
        return ""
    text = str(label).strip().lower()
    text = re.sub(r"[_\-\/\.\(\)\#\:]+", " ", text)
    return " ".join(text.split())


def detect_header_context(
    rows: list[SourceRow], max_scan_rows: int = 10
) -> tuple[HeaderContext, list[SourceRow]]:
    """Detect the header row, map duplicate column labels, and separate data rows.

    Never overwrites duplicate column names; maps all occurrences by zero-based index.
    """
    if not rows:
        empty_ctx = HeaderContext(
            candidate_rows=[],
            selected_row=1,
            raw_labels=[],
            normalized_labels=[],
            duplicate_labels=[],
            label_to_indices={},
            confidence="low",
            reasons=["No rows provided."],
        )
        return empty_ctx, []

    candidates: list[tuple[int, int, list[str]]] = []
    scan_limit = min(len(rows), max_scan_rows)

    for idx in range(scan_limit):
        row = rows[idx]
        cells = [str(c).strip() for c in row.cells if c is not None and str(c).strip()]
        if not cells:
            continue

        normalized = [normalize_header(c) for c in cells]
        score = sum(
            1 for norm in normalized if any(kw in norm for kw in KNOWN_HEADER_KEYWORDS)
        )

        if score >= 3:
            candidates.append((row.row_number, score, [str(c) for c in row.cells]))

    if not candidates:
        # Fallback to row 1 if no strong candidate found
        selected_row_num = rows[0].row_number
        raw_labels = [str(c) if c is not None else "" for c in rows[0].cells]
        confidence: Confidence = "low"
        reasons = ["No strong keyword matches found in initial rows; defaulted to row 1."]
    else:
        # Select candidate with highest keyword match score
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected_row_num = candidates[0][0]
        raw_labels = candidates[0][2]
        confidence = "high" if candidates[0][1] >= 5 else "medium"
        reasons = [f"Selected row {selected_row_num} with keyword score {candidates[0][1]}."]

    normalized_labels = [normalize_header(c) for c in raw_labels]

    label_to_indices: dict[str, list[int]] = {}
    duplicate_labels_set: set[str] = set()

    for col_idx, norm_label in enumerate(normalized_labels):
        if not norm_label:
            continue
        if norm_label in label_to_indices:
            label_to_indices[norm_label].append(col_idx)
            duplicate_labels_set.add(norm_label)
        else:
            label_to_indices[norm_label] = [col_idx]

    context = HeaderContext(
        candidate_rows=[c[0] for c in candidates],
        selected_row=selected_row_num,
        raw_labels=raw_labels,
        normalized_labels=normalized_labels,
        duplicate_labels=sorted(duplicate_labels_set),
        label_to_indices=label_to_indices,
        confidence=confidence,
        reasons=reasons,
    )

    # Separate rows into data rows (after header) and attach context
    data_rows: list[SourceRow] = []
    for r in rows:
        if r.row_number <= selected_row_num:
            # Header or preamble row
            continue
        r.header_context = context
        data_rows.append(r)

    return context, data_rows

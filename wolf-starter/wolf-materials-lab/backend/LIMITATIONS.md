# Known Limitations and Residual Risks

This document records the operational limitations, unsupported formats, and residual risks for the Wolf Materials Lab reconciliation, decision, and approval system as established in Phase Nine.

---

## 1. Known Limitations

### 1.1 Synthetic Data Boundary
- All demo data, spend transactions, invoices, and rate cards are 100% synthetically generated.
- No real customer names, supplier credentials, or banking details exist in the system.
- External actions (e.g. ERP sync, procurement order placement) are executed as mock-only records (`MockAction`) in the database, with no active outbound network connections.

### 1.2 Layout & Format Scope
- **Supported File Formats**: Delimited CSV (UTF-8, UTF-8 with BOM, and Latin-1 fallback).
- **Unsupported Formats**: Binary spreadsheets (`.xlsx`, `.xls`), scanned PDFs, or password-protected archives require preprocessing or tabular export prior to ingestion.
- **Header & Layout Detection**: Optimized for standard spend layouts (18 columns) and the France v2 delivery sheet (34 columns). Unrecognized layouts are classified with low confidence and routed to the human review queue.

### 1.3 Currency and Unit Homogeneity
- **Strict Decimal Arithmetic**: Floating-point math is strictly forbidden; all financial aggregations use Python `Decimal`.
- **Currency Single-Tenant Invariant**: Benefit calculations require comparable records to share a single currency (EUR for French market). Cross-currency calculations raise explicit validation exceptions rather than applying speculative conversions.
- **Unit Equivalence**: Box-versus-piece or pack-versus-unit comparisons require explicit catalog conversion factors; otherwise, calculations abstain with `insufficient_evidence`.

### 1.4 Optimistic Concurrency & Replay
- Approval operations require an exact match of `calculation_hash`. Any background modification, new correction, or upstream source ingestion immediately invalidates existing drafts with HTTP 409 Conflict.
- Replaying events is idempotent only when the identical event key and payload hash are supplied. Submitting differing payloads under an existing event key is rejected as an idempotency conflict.

---

## 2. Residual Risks and Mitigations

| Risk | Impact | Automated Mitigation | Reviewer Action Required |
| :--- | :--- | :--- | :--- |
| **Supplier Scope Leakage** | Incoming file contains lines from suppliers outside declared scope. | Scope validator flags `out_of_scope_record` and rejects replacement. | Reviewer must inspect the delivery and adjust scope or reject incoming batch. |
| **Repeated Invoice Totals** | Header summaries repeated on each row distort spend totals. | Line classifier isolates `invoice_total` and excludes it from summation with reason code `invoice_total_excluded`. | None needed; line arithmetic operates strictly on line items. |
| **Unlinked Cancellations** | Credit notes without direct PO or prior invoice reference. | Lineage engine marks unlinked credit notes and records signed negative values. | Reviewer can link credit note to prior invoice via append-only correction. |
| **Formula Injection** | Cells starting with `=, +, -, @` execute arbitrary macros in spreadsheets. | CSV reader sanitizes cell text as literal strings; never evaluated. | None. |
| **Path Traversal in Uploads** | Hostile filenames (`../../etc/shadow`) attempt storage escape. | Upload endpoint sanitizes filename to strict basename (`Path(name).name`). | None. |
| **Ambiguous Product Codes** | Incomplete article codes prevent catalog lookup. | Decision engine abstains with `insufficient_evidence`; cannot fabricate savings. | Reviewer enters verified product code in Review Queue. |

---

## 3. Verification Commands

To verify that the system satisfies all invariants from a clean environment:

```bash
# 1. Static typing and lint checks
poetry check
poetry run ruff check .
poetry run mypy app

# 2. Acceptance and full test suite
poetry run pytest tests/acceptance -q
poetry run pytest -q

# 3. Evidence completeness and provenance audit
poetry run python -m app.verification.evidence_check
```

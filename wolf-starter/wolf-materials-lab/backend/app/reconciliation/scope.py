"""Update-scope validation. Scope is a safety boundary, never an inference."""

from app.reconciliation.contracts import ReconciliationIssue, ReconciliationRecord, UpdateScope


def validate_update_scope(
    previous: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    incoming: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    scope: UpdateScope,
) -> tuple[ReconciliationIssue, ...]:
    issues: list[ReconciliationIssue] = []
    if scope.update_mode != "replacement":
        issues.append(ReconciliationIssue("unsupported_update_mode", f"Unsupported update mode: {scope.update_mode}"))
    if not scope.market:
        issues.append(ReconciliationIssue("missing_scope_evidence", "Scope market is required."))
    if not scope.supplier_ids and not scope.full_market:
        issues.append(ReconciliationIssue("missing_scope_evidence", "Replacement supplier scope cannot be empty."))
    if scope.full_market:
        issues.append(ReconciliationIssue("expanded_scope", "Full-market replacement requires explicit authorization."))
    if not scope.evidence:
        issues.append(ReconciliationIssue("missing_scope_evidence", "Scope must include source evidence."))

    allowed = set(scope.supplier_ids)
    for record in (*previous, *incoming):
        if record.market != scope.market:
            issues.append(ReconciliationIssue("cross_market_record", f"Record {record.record_id} is outside market scope."))
    for record in incoming:
        if record.supplier_id not in allowed:
            issues.append(ReconciliationIssue("out_of_scope_record", f"Incoming record {record.record_id} is outside supplier scope."))
        if not record.evidence:
            issues.append(ReconciliationIssue("missing_record_evidence", f"Incoming record {record.record_id} has no evidence."))
    return tuple(issues)


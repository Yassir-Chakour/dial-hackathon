"""Pure supplier-subset replacement transformation."""

from dataclasses import dataclass

from app.reconciliation.contracts import MaterializedRecord, ReconciliationIssue, ReconciliationRecord, UpdateScope
from app.reconciliation.identity import build_record_identity, match_records
from app.reconciliation.scope import validate_update_scope


@dataclass(frozen=True)
class ApplyResult:
    records: tuple[MaterializedRecord, ...]
    issues: tuple[ReconciliationIssue, ...]

    @property
    def accepted(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def apply_replacement(
    previous: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    incoming: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    scope: UpdateScope,
) -> ApplyResult:
    issues = list(validate_update_scope(previous, incoming, scope))
    if any(issue.severity == "error" for issue in issues):
        return ApplyResult((), tuple(issues))

    allowed = set(scope.supplier_ids)
    prior_in_scope = [record for record in previous if record.supplier_id in allowed]
    prior_out_of_scope = [record for record in previous if record.supplier_id not in allowed]
    matches = match_records(prior_in_scope, list(incoming))
    issues.extend(matches.issues)
    if matches.issues:
        return ApplyResult((), tuple(issues))

    materialized = [MaterializedRecord(record, "preserved_from_previous") for record in prior_out_of_scope]
    for record in incoming:
        key = build_record_identity(record)
        prior = next((old for old, new in matches.matched if build_record_identity(new) == key), None)
        materialized.append(MaterializedRecord(record, "replaced_previous_record" if prior else "introduced_by_incoming", prior.record_id if prior else None))
    materialized.sort(key=lambda item: build_record_identity(item.record))
    return ApplyResult(tuple(materialized), tuple(issues))


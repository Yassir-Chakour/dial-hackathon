"""Structured change-set generation from a validated materialization."""

from decimal import Decimal

from app.reconciliation.contracts import ChangeSet, MaterializedRecord, RecordChange, ReconciliationRecord, UpdateScope
from app.reconciliation.identity import build_record_identity


def build_change_set(
    previous_version_id: str,
    incoming_version_id: str,
    current_version_id: str | None,
    scope: UpdateScope,
    previous: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    incoming: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    current: list[MaterializedRecord] | tuple[MaterializedRecord, ...],
) -> ChangeSet:
    previous_by_key = {build_record_identity(record): record for record in previous}
    incoming_by_key = {build_record_identity(record): record for record in incoming}
    current_by_key = {build_record_identity(item.record): item for item in current}
    added: list[RecordChange] = []
    replaced: list[RecordChange] = []
    removed: list[RecordChange] = []
    preserved: list[RecordChange] = []

    for key in sorted(incoming_by_key):
        new = incoming_by_key[key]
        old = previous_by_key.get(key)
        change = RecordChange(key, "replaced" if old else "added", old.record_id if old else None, new.record_id,
                              _amount(old), _amount(new), "in_scope_replacement" if old else "new_record",
                              new.evidence, True)
        (replaced if old else added).append(change)
    for key in sorted(previous_by_key):
        old = previous_by_key[key]
        if key in current_by_key and key not in incoming_by_key:
            preserved.append(RecordChange(key, "preserved", old.record_id, None, _amount(old), _amount(old),
                                          "preserved_outside_scope", old.evidence, False))
        elif key not in current_by_key:
            removed.append(RecordChange(key, "removed_from_current", old.record_id, None, _amount(old), None,
                                        "prior_record_superseded", old.evidence, True))
    return ChangeSet(previous_version_id, incoming_version_id, current_version_id, scope,
                     tuple(added), tuple(replaced), tuple(removed), tuple(preserved))


def _amount(record: ReconciliationRecord | None) -> Decimal | None:
    return None if record is None or record.value is None else Decimal(str(record.value))

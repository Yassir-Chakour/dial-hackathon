"""Pure Decimal-only procurement benefit calculations."""

from decimal import Decimal
import hashlib
import json
from typing import Any

from app.decisions.contracts import DecisionCategory, DecisionInputSnapshot, DecisionRecord, DecisionResult


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_decision_input_snapshot(
    *, reconciliation_version_id: str, source_version_ids: tuple[str, ...],
    change_set_id: str | None = None, corrections: tuple[tuple[str, Any], ...] = (),
    assumptions: tuple[tuple[str, str], ...] = (), calculation_version: str = "phase-six-v1",
) -> DecisionInputSnapshot:
    """Create an immutable input snapshot with a stable canonical hash."""
    draft = DecisionInputSnapshot(reconciliation_version_id, tuple(sorted(source_version_ids)), change_set_id,
                                  tuple(sorted(corrections)), tuple(sorted(assumptions)), calculation_version)
    return DecisionInputSnapshot(**{**draft.__dict__, "input_hash": _hash(draft.payload())})


def calculate_decision_facts(snapshot: DecisionInputSnapshot, records: tuple[DecisionRecord, ...] | list[DecisionRecord]) -> DecisionResult:
    """Calculate one deterministic aggregate, rejecting unsupported facts."""
    rows = tuple(records)
    payload = {"snapshot": snapshot.payload(), "records": [r.__dict__ for r in rows]}
    if not rows:
        return _result(snapshot, payload, "insufficient_evidence", None, None, None, ("no_records",), (), False)
    if any(r.validation_status != "valid" or r.ambiguous for r in rows):
        return _result(snapshot, payload, "insufficient_evidence", None, None, None,
                       ("invalid_or_ambiguous_record",), ("Calculation excluded rejected or ambiguous records.",), False)
    if any(not r.evidence_ids for r in rows):
        return _result(snapshot, payload, "insufficient_evidence", None, None, None,
                       ("evidence_missing",), ("Evidence is incomplete; reviewer action is required.",), False)
    currencies = {r.currency for r in rows}
    units = {r.unit for r in rows}
    if len(currencies) != 1:
        raise ValueError("currency_mismatch: comparable records must use one currency")
    if len(units) != 1:
        raise ValueError("unit_mismatch: comparable records must use one unit")
    if any(r.baseline_value is None for r in rows):
        return _result(snapshot, payload, "not_comparable", None, rows[0].currency, rows[0].unit,
                       ("baseline_missing",), ("A defined comparable baseline is required.",), False)
    amount = sum(((r.baseline_value or Decimal("0")) - r.value for r in rows), Decimal("0"))
    category: DecisionCategory = "recurring_saving" if amount >= 0 else "price_change"
    return _result(snapshot, payload, category, amount, rows[0].currency, rows[0].unit,
                   ("comparable_baseline",), (), True)


def _result(snapshot: DecisionInputSnapshot, payload: Any, category: DecisionCategory, amount: Decimal | None,
            currency: str | None, unit: str | None, reasons: tuple[str, ...], warnings: tuple[str, ...],
            evidence_complete: bool) -> DecisionResult:
    result = DecisionResult(category, amount, currency, unit, reasons, warnings, evidence_complete)
    return DecisionResult(**{**result.__dict__, "result_hash": _hash({"snapshot_hash": snapshot.input_hash, "result": result.as_dict()})})


from decimal import Decimal

import pytest

from app.decisions.calculator import build_decision_input_snapshot, calculate_decision_facts
from app.decisions.contracts import DecisionRecord


def _snapshot():
    return build_decision_input_snapshot(reconciliation_version_id="run-1", source_version_ids=("v-1",))


def test_comparable_baseline_is_a_decimal_saving_with_stable_hash():
    record = DecisionRecord("r1", "bolt", "bolt", "supplier", Decimal("2"), "kg", "EUR", Decimal("8"), Decimal("10"), evidence_ids=("e1",))
    first = calculate_decision_facts(_snapshot(), [record])
    second = calculate_decision_facts(_snapshot(), [record])
    assert first.category == "recurring_saving"
    assert first.amount == Decimal("2")
    assert first.result_hash == second.result_hash


def test_missing_evidence_is_review_not_zero():
    record = DecisionRecord("r1", "bolt", "bolt", "supplier", Decimal("2"), "kg", "EUR", Decimal("8"), Decimal("10"))
    result = calculate_decision_facts(_snapshot(), [record])
    assert result.category == "insufficient_evidence"
    assert result.amount is None
    assert not result.evidence_complete


def test_mismatched_currency_is_rejected():
    records = [DecisionRecord("1", "1", "p", "s", Decimal("1"), "kg", "EUR", Decimal("1"), Decimal("2"), evidence_ids=("e",)),
               DecisionRecord("2", "2", "p", "s", Decimal("1"), "kg", "USD", Decimal("1"), Decimal("2"), evidence_ids=("e",))]
    with pytest.raises(ValueError, match="currency_mismatch"):
        calculate_decision_facts(_snapshot(), records)

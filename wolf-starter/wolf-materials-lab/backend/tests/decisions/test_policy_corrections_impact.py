import pytest

from app.decisions.approval_policy import ApprovalPreconditionError, check_approval_preconditions
from app.decisions.contracts import ApprovalRequest
from app.decisions.corrections import validate_correction
from app.decisions.impact import find_impacted_recommendations


def _request(**overrides):
    values = dict(recommendation_id="rec-1", result_hash="r" * 64, input_hash="i" * 64,
                  reviewer_id="reviewer-1", reason="checked", expected_version=1, request_id="req-1")
    values.update(overrides)
    return ApprovalRequest(**values)


def _state(**overrides):
    values = dict(recommendation_id="rec-1", status="needs_review", result_hash="r" * 64,
                  input_hash="i" * 64, source_status="accepted", blocking_issue_ids=[],
                  evidence_complete=True, reviewer_authorized=True, newer_version_exists=False, version=1)
    values.update(overrides)
    return values


def test_exact_version_approval_policy_rejects_changed_input():
    with pytest.raises(ApprovalPreconditionError) as error:
        check_approval_preconditions(_request(input_hash="x" * 64), _state())
    assert error.value.code == "input_snapshot_changed"


def test_correction_is_validated_and_hashed_without_mutating_target():
    target = {"value": "10.00", "currency": "EUR"}
    result = validate_correction({"field_name": "value", "corrected_value": "9.50",
                                  "reviewer_id": "reviewer-1", "reason": "invoice checked"}, target)
    assert result["original_value"] == "10.00"
    assert result["correction_hash"]
    assert target["value"] == "10.00"


def test_impact_only_marks_dependent_record_or_evidence():
    records = [{"id": "rec-1", "record_keys": ["line-1"], "source_version_ids": ["v1"], "evidence_ids": ["e1"]},
               {"id": "rec-2", "record_keys": ["line-2"], "source_version_ids": ["v1"], "evidence_ids": ["e2"]}]
    changed = {"previous_version_id": "v1", "incoming_version_id": "v2", "replaced": [{"record_key": "line-1"}]}
    impacts = find_impacted_recommendations(records, changed)
    assert [item.recommendation_id for item in impacts] == ["rec-1"]

"""Server-side approval preconditions; client status is never trusted."""

from dataclasses import dataclass
from typing import Any

from app.decisions.contracts import ApprovalRequest


@dataclass(frozen=True)
class ApprovalPreconditionError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def check_approval_preconditions(request: ApprovalRequest, current_state: dict[str, Any]) -> None:
    request.bounded()
    if current_state.get("recommendation_id") != request.recommendation_id:
        raise ApprovalPreconditionError("recommendation_not_found", "Recommendation does not exist.")
    if current_state.get("status") != "needs_review":
        code = "recommendation_stale" if current_state.get("status") in {"stale", "superseded"} else "approval_conflict"
        raise ApprovalPreconditionError(code, "Recommendation is not the current approvable version.")
    checks = (("result_hash", "result_hash", "approval_conflict"), ("input_hash", "input_hash", "input_snapshot_changed"))
    for state_key, request_key, code in checks:
        if current_state.get(state_key) != getattr(request, request_key):
            raise ApprovalPreconditionError(code, "Approval hashes do not match current persisted inputs.")
    if current_state.get("source_status") != "accepted":
        raise ApprovalPreconditionError("source_version_not_accepted", "Source/reconciliation version is not accepted.")
    if current_state.get("blocking_issue_ids"):
        raise ApprovalPreconditionError("blocking_issues_present", "Blocking review issues remain.")
    if not current_state.get("evidence_complete", False):
        raise ApprovalPreconditionError("evidence_incomplete", "Required evidence links are incomplete.")
    if request.capability != "approve" or not current_state.get("reviewer_authorized", False):
        raise ApprovalPreconditionError("reviewer_not_authorized", "Reviewer lacks approval capability.")
    if current_state.get("newer_version_exists", False):
        raise ApprovalPreconditionError("newer_version_exists", "A newer recommendation exists for this decision key.")
    if current_state.get("version") != request.expected_version:
        raise ApprovalPreconditionError("approval_conflict", "Recommendation version changed during approval.")

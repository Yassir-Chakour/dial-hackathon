"""Approval repository with exact-version compare-and-swap semantics."""

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.models import Approval, Recommendation
from app.decisions.approval_policy import ApprovalPreconditionError, check_approval_preconditions
from app.decisions.contracts import ApprovalRequest


class ApprovalRepository:
    def commit_approval(self, session: Session, request: ApprovalRequest, state: dict[str, object]) -> Approval:
        recommendation = session.get(Recommendation, request.recommendation_id, with_for_update=True)
        if recommendation is None:
            raise ApprovalPreconditionError("recommendation_not_found", "Recommendation does not exist.")
        current = dict(state)
        current.update({"recommendation_id": recommendation.id, "status": recommendation.status,
                        "result_hash": recommendation.result_hash or recommendation.calculation_hash,
                        "input_hash": recommendation.input_hash, "version": recommendation.version})
        check_approval_preconditions(request, current)
        prior_status = recommendation.status
        recommendation.status = "approved"
        recommendation.version += 1
        approval = Approval(recommendation_id=recommendation.id, decision="approved", reviewer_id=request.reviewer_id,
                            reason=request.reason, calculation_hash=representation_hash(recommendation),
                            result_hash=recommendation.result_hash, input_snapshot_id=recommendation.input_snapshot_id,
                            input_hash=recommendation.input_hash, request_id=request.request_id)
        session.add(approval)
        session.flush()
        return approval


def representation_hash(recommendation: Recommendation) -> str:
    return recommendation.result_hash or recommendation.calculation_hash


def stale_approval(approval: Approval) -> None:
    approval.stale_at = datetime.now(timezone.utc)

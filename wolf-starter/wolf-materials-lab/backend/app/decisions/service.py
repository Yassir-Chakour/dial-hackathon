"""Transactional Phase Six orchestration."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Approval, AuditEventRow, Recommendation, RecommendationStatus
from app.decisions.audit import record_audit_event
from app.decisions.contracts import ApprovalRequest, DecisionInputSnapshot, RecommendationFacts
from app.decisions.impact import mark_recommendation_stale
from app.repositories.approvals import ApprovalRepository
from app.repositories.decisions import DecisionRepository


class DecisionService:
    def __init__(self, decisions: DecisionRepository | None = None, approvals: ApprovalRepository | None = None) -> None:
        self.decisions = decisions or DecisionRepository()
        self.approvals = approvals or ApprovalRepository()

    def create_recommendation(self, session: Session, *, source_version_id: str, recommendation_key: str,
                              snapshot: DecisionInputSnapshot, facts: RecommendationFacts,
                              parent_recommendation_id: str | None = None, tenant_id: str | None = None) -> Recommendation:
        self.decisions.create_input_snapshot(session, snapshot)
        row = self.decisions.create_recommendation(session, source_version_id=source_version_id,
                                                   recommendation_key=recommendation_key, snapshot=snapshot,
                                                   facts=facts, parent_recommendation_id=parent_recommendation_id,
                                                   tenant_id=tenant_id)
        self.record_audit(session, record_audit_event("recommendation_created", row.id, current_status=row.status,
                                                      input_hash=snapshot.input_hash, result_hash=facts.result_hash))
        return row

    def propagate_staleness(self, session: Session, *, source_version_id: str, reason: str,
                            recommendation_ids: set[str] | None = None) -> int:
        query = select(Recommendation).where(Recommendation.source_version_id == source_version_id,
            Recommendation.status.in_(["draft", "needs_review", "approved"]))
        rows = list(session.scalars(query))
        changed = 0
        for row in rows:
            if recommendation_ids is not None and row.id not in recommendation_ids:
                continue
            old = row.status
            mark_recommendation_stale(row, reason)
            changed += 1
            self.record_audit(session, record_audit_event("recommendation_marked_stale", row.id,
                previous_status=old, current_status=row.status, input_hash=row.input_hash,
                result_hash=row.result_hash, reason_codes=(reason,)))
        session.flush()
        return changed

    def approve(self, session: Session, request: ApprovalRequest, state: dict[str, object]) -> Approval:
        approval = self.approvals.commit_approval(session, request, state)
        self.record_audit(session, record_audit_event("approval_accepted", approval.recommendation_id,
            actor_id=request.reviewer_id, current_status="approved", input_hash=approval.input_hash,
            result_hash=approval.result_hash, policy_version=approval.policy_version, request_id=request.request_id))
        return approval

    @staticmethod
    def record_audit(session: Session, event: Any) -> AuditEventRow:
        row = AuditEventRow(id=event.event_id, event_type=event.event_type, actor_id=event.actor_id,
            target_id=event.target_id, previous_status=event.previous_status, current_status=event.current_status,
            input_hash=event.input_hash, result_hash=event.result_hash, policy_version=event.policy_version,
            reason_codes_json=list(event.reason_codes), request_id=event.request_id, created_at=event.created_at)
        session.add(row)
        session.flush()
        return row


def create_mock_action(session: Session, recommendation_id: str) -> Any:
    from app.db.models import MockAction
    action = MockAction(recommendation_id=recommendation_id, action_type="procurement_draft", status="draft",
                        payload_json={"external_send": False})
    session.add(action)
    session.flush()
    return action

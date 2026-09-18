"""Transactional Phase Six orchestration."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Approval, AuditEventRow, Correction, Recommendation, RecommendationItem
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
                            recommendation_ids: set[str] | None = None,
                            changed_record_ids: set[str] | None = None,
                            changed_evidence_ids: set[str] | None = None) -> int:
        query = select(Recommendation).where(Recommendation.source_version_id == source_version_id,
            Recommendation.status.in_(["draft", "needs_review", "approved"]))
        rows = list(session.scalars(query))
        changed = 0
        for row in rows:
            if recommendation_ids is not None and row.id not in recommendation_ids:
                continue
            if changed_record_ids is not None or changed_evidence_ids is not None:
                items = list(session.scalars(select(RecommendationItem).where(
                    RecommendationItem.recommendation_id == row.id)))
                record_match = any(changed_record_ids and changed_record_ids.intersection(item.input_record_ids_json)
                                   for item in items)
                evidence_match = any(changed_evidence_ids and changed_evidence_ids.intersection(
                    [str(entry.get("id")) for entry in item.evidence_json]) for item in items)
                if not (record_match or evidence_match):
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
        try:
            approval = self.approvals.commit_approval(session, request, state)
        except Exception:
            # The caller's transaction may choose to persist this event in a
            # separate audit transaction; never expose internal exceptions as
            # an approval result.
            raise
        self.record_audit(session, record_audit_event("approval_accepted", approval.recommendation_id,
            actor_id=request.reviewer_id, current_status="approved", input_hash=approval.input_hash,
            result_hash=approval.result_hash, policy_version=approval.policy_version, request_id=request.request_id))
        return approval

    def recalculate_after_correction(self, session: Session, *, correction_id: str,
                                     recommendation_id: str, source_version_id: str,
                                     snapshot: DecisionInputSnapshot, facts: RecommendationFacts) -> Recommendation:
        correction = session.get(Correction, correction_id)
        if correction is None:
            raise ValueError("correction_not_found")
        if correction.status != "accepted":
            raise ValueError("correction_not_accepted")
        old = session.get(Recommendation, recommendation_id, with_for_update=True)
        if old is None:
            raise ValueError("recommendation_not_found")
        old_status = old.status
        mark_recommendation_stale(old, "reviewer_correction")
        self.record_audit(session, record_audit_event("correction_accepted", correction.id,
            actor_id=correction.reviewer_id, reason_codes=("reviewer_correction",)))
        self.record_audit(session, record_audit_event("recommendation_marked_stale", old.id,
            previous_status=old_status, current_status=old.status, input_hash=old.input_hash,
            result_hash=old.result_hash, reason_codes=("reviewer_correction",)))
        row = self.create_recommendation(session, source_version_id=source_version_id,
            recommendation_key=f"{old.recommendation_key}:v{old.version + 1}", snapshot=snapshot, facts=facts,
            parent_recommendation_id=old.id, tenant_id=old.tenant_id)
        row.version = old.version + 1
        session.flush()
        return row

    def reject(self, session: Session, recommendation_id: str, *, reviewer_id: str, reason: str,
               request_id: str | None = None) -> Approval:
        if not reason or len(reason) > 1000:
            raise ValueError("rejection reason must be between 1 and 1000 characters")
        recommendation = session.get(Recommendation, recommendation_id, with_for_update=True)
        if recommendation is None:
            raise ValueError("recommendation_not_found")
        if recommendation.status in {"approved", "stale", "superseded"}:
            raise ValueError("recommendation_not_rejectable")
        previous = recommendation.status
        recommendation.status = "rejected"
        approval = Approval(recommendation_id=recommendation.id, decision="rejected", reviewer_id=reviewer_id,
                            reason=reason, calculation_hash=recommendation.result_hash or recommendation.calculation_hash,
                            result_hash=recommendation.result_hash, input_snapshot_id=recommendation.input_snapshot_id,
                            input_hash=recommendation.input_hash, request_id=request_id)
        session.add(approval)
        session.flush()
        self.record_audit(session, record_audit_event("recommendation_rejected", recommendation.id,
            actor_id=reviewer_id, previous_status=previous, current_status="rejected",
            input_hash=recommendation.input_hash, result_hash=recommendation.result_hash,
            reason_codes=("reviewer_rejected",), request_id=request_id))
        return approval

    def revoke_approval(self, session: Session, approval_id: str, *, actor_id: str, reason: str,
                        request_id: str | None = None) -> Approval:
        if not reason or len(reason) > 1000:
            raise ValueError("revocation reason must be between 1 and 1000 characters")
        approval = session.get(Approval, approval_id, with_for_update=True)
        if approval is None or approval.decision != "approved":
            raise ValueError("approval_not_found")
        approval.stale_at = datetime.now(timezone.utc)
        self.record_audit(session, record_audit_event("approval_revoked", approval.recommendation_id,
            actor_id=actor_id, reason_codes=("operational_revocation",), request_id=request_id))
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
    DecisionService.record_audit(session, record_audit_event("mock_external_action_created", recommendation_id,
        current_status="draft", reason_codes=("external_send_disabled",)))
    return action

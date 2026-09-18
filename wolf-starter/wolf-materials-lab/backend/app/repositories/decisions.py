"""Safe repository operations for immutable decision projections."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DecisionInputSnapshotRow, Recommendation, RecommendationItem, RecommendationStatus
from app.decisions.contracts import DecisionInputSnapshot, RecommendationFacts


class DecisionRepository:
    def create_input_snapshot(self, session: Session, snapshot: DecisionInputSnapshot) -> DecisionInputSnapshotRow:
        existing = session.scalar(select(DecisionInputSnapshotRow).where(
            DecisionInputSnapshotRow.input_hash == snapshot.input_hash))
        if existing is not None:
            return existing
        row = DecisionInputSnapshotRow(
            reconciliation_version_id=snapshot.reconciliation_version_id,
            source_version_ids_json=list(snapshot.source_version_ids), change_set_id=snapshot.change_set_id,
            corrections_json=[{"key": key, "value": value} for key, value in snapshot.corrections],
            assumptions_json=[{"key": key, "value": value} for key, value in snapshot.assumptions],
            calculation_version=snapshot.calculation_version, input_hash=snapshot.input_hash,
            created_at=snapshot.created_at,
        )
        session.add(row)
        session.flush()
        return row

    def create_recommendation(self, session: Session, *, source_version_id: str, recommendation_key: str,
                              snapshot: DecisionInputSnapshot, facts: RecommendationFacts,
                              parent_recommendation_id: str | None = None, tenant_id: str | None = None) -> Recommendation:
        # Every constructed recommendation enters the explicit reviewer queue.
        # ``draft`` remains available for partially assembled projections, but
        # a persisted recommendation cannot be approved before review.
        status = RecommendationStatus.NEEDS_REVIEW.value
        row = Recommendation(source_version_id=source_version_id, input_snapshot_id=None,
            recommendation_key=recommendation_key, recommendation_key_stable=recommendation_key, status=status,
            facts_json={"summary": facts.summary, "items": list(facts.items), "assumptions": list(facts.assumptions),
                        "uncertainties": list(facts.uncertainties), "evidence_ids": list(facts.evidence_ids)},
            explanation_json={}, calculation_hash=facts.result_hash, result_hash=facts.result_hash,
            input_hash=snapshot.input_hash, blocking_issue_ids_json=list(facts.blocking_issue_ids),
            evidence_complete=facts.evidence_complete, parent_recommendation_id=parent_recommendation_id,
            tenant_id=tenant_id)
        session.add(row)
        session.flush()
        row.input_snapshot_id = self._snapshot_id(session, snapshot.input_hash)
        for item in facts.items:
            session.add(RecommendationItem(recommendation_id=row.id, product_key=str(item["record_key"]),
                supplier=item.get("supplier"), quantity=item.get("quantity"), unit=item.get("unit"),
                currency=item.get("currency"), value=item.get("value"), outcome="included",
                evidence_json=[{"id": evidence_id} for evidence_id in item.get("evidence_ids", [])],
                input_record_ids_json=[str(item["record_id"])]))
        session.flush()
        return row

    def _snapshot_id(self, session: Session, input_hash: str) -> str:
        row = session.scalar(select(DecisionInputSnapshotRow).where(DecisionInputSnapshotRow.input_hash == input_hash))
        if row is None:
            raise ValueError("Input snapshot was not persisted")
        return row.id

    def get_current_versions(self, session: Session, recommendation_key: str) -> list[Recommendation]:
        return list(session.scalars(select(Recommendation).where(
            Recommendation.recommendation_key_stable == recommendation_key,
            Recommendation.status.not_in([RecommendationStatus.SUPERSEDED.value]),
        ).order_by(Recommendation.version.desc())))

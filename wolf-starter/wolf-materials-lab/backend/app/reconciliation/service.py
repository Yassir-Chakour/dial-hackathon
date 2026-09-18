"""Transactional orchestration for one reconciliation event."""

from dataclasses import dataclass
from typing import Any
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    EventStatus,
    MaterializedRecord as MaterializedRecordRow,
    ReconciliationIssueRecord,
    ReconciliationRun,
    SourceRecord,
    SourceStatus,
    SourceVersion,
    now_utc,
)
from app.persistence import EventRepository, sha256_payload
from app.reconciliation.adapters import from_persisted_record
from app.reconciliation.apply import ApplyResult, apply_replacement
from app.reconciliation.changes import build_change_set
from app.reconciliation.contracts import ReconciliationIssue, ReconciliationRecord, UpdateScope
from app.reconciliation.identity import build_record_identity, canonical_record_payload, compute_reconciliation_hash
from app.reconciliation.totals import reconcile_totals


@dataclass(frozen=True)
class ReconciliationOutcome:
    run: ReconciliationRun | None
    event_replayed: bool
    status: str
    result_hash: str | None
    issues: tuple[ReconciliationIssue, ...] = ()


class ReconciliationService:
    """Loads validated Phase Three records and commits one immutable snapshot."""

    algorithm_version = "phase-four-v1"

    def get_run(self, session: Session, run_id: str) -> ReconciliationRun | None:
        """Read one immutable reconciliation audit result."""
        return session.get(ReconciliationRun, run_id)

    def get_materialized_records(self, session: Session, run_id: str) -> list[MaterializedRecordRow]:
        """Read the current materialization in stable business-key order."""
        return list(session.scalars(select(MaterializedRecordRow).where(
            MaterializedRecordRow.reconciliation_run_id == run_id,
        ).order_by(MaterializedRecordRow.record_key)))

    def reconcile_versions(
        self,
        session: Session,
        *,
        event_key: str,
        payload: Any,
        previous_version_id: str,
        incoming_version_id: str,
        scope: UpdateScope,
        tenant_id: str | None = None,
        expected_total: Decimal | str | None = None,
    ) -> ReconciliationOutcome:
        """Load persisted Phase Two inputs, then run the pure reconciliation path."""
        previous_rows = list(session.scalars(select(SourceRecord).where(
            SourceRecord.source_version_id == previous_version_id,
        ).order_by(SourceRecord.source_row_number)))
        incoming_rows = list(session.scalars(select(SourceRecord).where(
            SourceRecord.source_version_id == incoming_version_id,
        ).order_by(SourceRecord.source_row_number)))
        return self.reconcile(
            session,
            event_key=event_key,
            payload=payload,
            previous_version_id=previous_version_id,
            incoming_version_id=incoming_version_id,
            scope=scope,
            previous_records=[from_persisted_record(row) for row in previous_rows],
            incoming_records=[from_persisted_record(row) for row in incoming_rows],
            tenant_id=tenant_id,
            expected_total=expected_total,
        )

    def __init__(self, events: EventRepository | None = None) -> None:
        self.events = events or EventRepository()

    def reconcile(
        self,
        session: Session,
        *,
        event_key: str,
        payload: Any,
        previous_version_id: str,
        incoming_version_id: str,
        scope: UpdateScope,
        previous_records: list[ReconciliationRecord],
        incoming_records: list[ReconciliationRecord],
        tenant_id: str | None = None,
        expected_total: Decimal | str | None = None,
    ) -> ReconciliationOutcome:
        event_result = self.events.create_or_get_event(
            session,
            event_key=event_key,
            payload_hash=sha256_payload(payload),
            event_type="reconciliation.accept",
            tenant_id=tenant_id,
            source_version_id=incoming_version_id,
        )
        if event_result.replayed:
            run = session.scalar(select(ReconciliationRun).where(ReconciliationRun.event_id == event_result.event.id))
            if run is None:
                raise RuntimeError("Idempotent reconciliation event points to a missing run.")
            return ReconciliationOutcome(run, True, run.status, run.result_hash)

        issues = list(self._validate_versions(session, previous_version_id, incoming_version_id, scope))
        applied: ApplyResult | None = None
        if not issues:
            applied = apply_replacement(previous_records, incoming_records, scope)
            issues.extend(applied.issues)
        if issues:
            self._persist_issues(session, event_result.event.id, issues)
            self._mark_review(event_result.event, issues)
            return ReconciliationOutcome(None, False, "needs_review", None, tuple(issues))

        assert applied is not None
        preserved = [item.record for item in applied.records if item.lineage == "preserved_from_previous"]
        current_records = [item.record for item in applied.records]
        totals_ok, total_issues, preserved_totals, incoming_totals, current_totals = reconcile_totals(
            preserved, incoming_records, current_records
        )
        if not totals_ok:
            self._persist_issues(session, event_result.event.id, total_issues)
            self._mark_review(event_result.event, total_issues)
            return ReconciliationOutcome(None, False, "needs_review", None, total_issues)
        if expected_total is not None and current_totals.total != Decimal(str(expected_total)):
            issue = ReconciliationIssue(
                "expected_total_mismatch",
                f"Current total {current_totals.total} does not match expected fixture total {expected_total}.",
            )
            self._persist_issues(session, event_result.event.id, (issue,))
            self._mark_review(event_result.event, (issue,))
            return ReconciliationOutcome(None, False, "needs_review", None, (issue,))

        changes = build_change_set(previous_version_id, incoming_version_id, None, scope,
                                   previous_records, incoming_records, applied.records)
        result_hash = compute_reconciliation_hash({
            "algorithm_version": self.algorithm_version,
            "previous_version_id": previous_version_id,
            "incoming_version_id": incoming_version_id,
            "expected_total": str(expected_total) if expected_total is not None else None,
            "scope": {"market": scope.market, "supplier_ids": sorted(scope.supplier_ids), "update_mode": scope.update_mode},
            "previous": sorted((canonical_record_payload(r) for r in previous_records), key=lambda item: str(item["key"])),
            "incoming": sorted((canonical_record_payload(r) for r in incoming_records), key=lambda item: str(item["key"])),
        })
        run = ReconciliationRun(
            event_id=event_result.event.id,
            previous_version_id=previous_version_id,
            incoming_version_id=incoming_version_id,
            scope_key=f"{scope.market}:{','.join(sorted(scope.supplier_ids))}",
            status="accepted",
            result_hash=result_hash,
            scope_json={"market": scope.market, "supplier_ids": list(scope.supplier_ids), "update_mode": scope.update_mode},
            totals_json={"preserved": _totals_json(preserved_totals), "incoming": _totals_json(incoming_totals), "current": _totals_json(current_totals)},
            changes_json=_changes_json(changes),
        )
        session.add(run)
        session.flush()
        for item in applied.records:
            record = item.record
            session.add(MaterializedRecordRow(
                reconciliation_run_id=run.id,
                record_key=build_record_identity(record),
                source_record_id=record.record_id,
                prior_record_id=item.prior_record_id,
                lineage=item.lineage,
                supplier_id=record.supplier_id,
                product_id=record.product_id,
                value=str(record.value) if record.value is not None else None,
                currency=record.currency,
                unit=record.unit,
                record_kind=record.record_kind,
                evidence_json=[ref.__dict__ for ref in record.evidence],
            ))
        self.events.replace_event_status(event_result.event, EventStatus.PROCESSING)
        self.events.replace_event_status(event_result.event, EventStatus.COMPLETED)
        previous = session.get(SourceVersion, previous_version_id)
        incoming = session.get(SourceVersion, incoming_version_id)
        if previous is not None:
            previous.status = SourceStatus.SUPERSEDED.value
            previous.superseded_at = now_utc()
        if incoming is not None:
            incoming.status = SourceStatus.ACCEPTED.value
            incoming.accepted_at = incoming.accepted_at or now_utc()
        session.flush()
        # The prior source version is the dependency of existing decisions.
        # Only those recommendations are invalidated; unrelated decision keys
        # remain current and historical approvals remain inspectable.
        from app.decisions.service import DecisionService
        DecisionService().propagate_staleness(
            session, source_version_id=previous_version_id, reason="source_version_changed"
        )
        return ReconciliationOutcome(run, False, "accepted", result_hash)

    def _validate_versions(self, session: Session, previous_id: str, incoming_id: str,
                           scope: UpdateScope) -> tuple[ReconciliationIssue, ...]:
        issues: list[ReconciliationIssue] = []
        previous = session.get(SourceVersion, previous_id, with_for_update=True)
        incoming = session.get(SourceVersion, incoming_id, with_for_update=True)
        if previous is None:
            issues.append(ReconciliationIssue("missing_previous_version", "Previous version does not exist."))
        elif previous.status != SourceStatus.ACCEPTED.value:
            issues.append(ReconciliationIssue("previous_version_not_accepted", "Previous version is not accepted."))
        if incoming is None:
            issues.append(ReconciliationIssue("missing_incoming_version", "Incoming version does not exist."))
        elif incoming.status not in {SourceStatus.ACCEPTED.value, SourceStatus.RECEIVED.value}:
            issues.append(ReconciliationIssue("incoming_version_not_usable", "Incoming version cannot be reconciled."))
        if previous and incoming and previous.market != incoming.market:
            issues.append(ReconciliationIssue("cross_market_record", "Previous and incoming markets differ."))
        if previous and previous.market != scope.market:
            issues.append(ReconciliationIssue("cross_market_record", "Scope market differs from previous version."))
        if previous and incoming and previous.scope_key == incoming.scope_key:
            # Older accepted versions are immutable history, not concurrent
            # writers. Only an accepted version committed after the version
            # selected for this run can invalidate its optimistic check.
            accepted = list(session.scalars(select(SourceVersion).where(
                SourceVersion.scope_key == previous.scope_key,
                SourceVersion.tenant_id == previous.tenant_id,
                SourceVersion.status == SourceStatus.ACCEPTED.value,
                SourceVersion.id != incoming_id,
                SourceVersion.accepted_at > previous.accepted_at,
            )))
            if accepted:
                issues.append(ReconciliationIssue(
                    "concurrent_version_change",
                    "The expected current version changed before reconciliation committed.",
                ))
        return tuple(issues)

    def _persist_issues(self, session: Session, event_id: str,
                        issues: list[ReconciliationIssue] | tuple[ReconciliationIssue, ...]) -> None:
        for issue in issues:
            session.add(ReconciliationIssueRecord(
                event_id=event_id,
                code=issue.code,
                severity=issue.severity,
                message=issue.message[:512],
                evidence_json=[ref.__dict__ for ref in issue.evidence],
            ))

    def _mark_review(self, event: Any, issues: list[ReconciliationIssue] | tuple[ReconciliationIssue, ...]) -> None:
        first = issues[0]
        self.events.replace_event_status(event, EventStatus.NEEDS_REVIEW, error_code=first.code, error_summary=first.message)


def _totals_json(totals: Any) -> dict[str, Any]:
    return {"total": str(totals.total), "by_currency": {key: str(value) for key, value in totals.by_currency.items()},
            "credits": str(totals.credits), "cancellations": str(totals.cancellations),
            "excluded_invoice_totals": str(totals.excluded_invoice_totals),
            "included_record_count": totals.included_record_count, "excluded_record_count": totals.excluded_record_count}


def _changes_json(changes: Any) -> dict[str, Any]:
    def serialize(items: Any) -> list[dict[str, Any]]:
        return [{"record_key": item.record_key, "change_type": item.change_type,
                 "prior_record_id": item.prior_record_id, "incoming_record_id": item.incoming_record_id,
                 "old_value": str(item.old_value) if item.old_value is not None else None,
                 "new_value": str(item.new_value) if item.new_value is not None else None,
                 "reason_code": item.reason_code, "evidence": [ref.__dict__ for ref in item.evidence]}
                for item in items]
    return {"added": serialize(changes.added), "replaced": serialize(changes.replaced),
            "removed_from_current": serialize(changes.removed_from_current), "preserved": serialize(changes.preserved)}

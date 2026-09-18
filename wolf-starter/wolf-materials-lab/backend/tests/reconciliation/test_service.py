from decimal import Decimal
import pytest

from app.config import Settings
from app.db.models import ReconciliationIssueRecord, ReconciliationRun, MaterializedRecord, SourceStatus
from app.db.session import create_database
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord, UpdateScope
from app.reconciliation.service import ReconciliationService
from app.persistence import IdempotencyConflictError, SourceService


def _record(record_id: str, version_id: str, supplier: str, value: str, row: int, key: str) -> ReconciliationRecord:
    return ReconciliationRecord(
        record_id=record_id, version_id=version_id, market="FR", supplier_id=supplier,
        product_id="bolt", value=Decimal(value), currency="EUR", source_line_id=key,
        source_row_number=row, evidence=(EvidenceRef(version_id, record_id, row),), record_key=key,
    )


def test_reconciliation_service_commits_one_snapshot_and_replays(tmp_path) -> None:
    database = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'reconcile.db'}"))
    database.create_schema()
    try:
        source = SourceService()
        with database.transaction() as session:
            previous, _, _ = source.accept_version(
                session, content=b"previous", filename="previous.csv", media_type="text/csv",
                market="FR", version_label="v1", scope_key="FR", event_key="source-v1", payload={},
                records=[{"record_key": "line-1", "source_row_number": 2, "raw_values_json": {}, "supplier": "supplier-new"}],
            )
            incoming, _, _ = source.accept_version(
                session, content=b"incoming", filename="incoming.csv", media_type="text/csv",
                market="FR", version_label="v2", scope_key="FR", event_key="source-v2", payload={},
                records=[{"record_key": "line-1", "source_row_number": 2, "raw_values_json": {}, "supplier": "supplier-new"}],
            )
            service = ReconciliationService()
            outcome = service.reconcile_versions(
                session, event_key="reconcile-1", payload={"incoming": incoming.id},
                previous_version_id=previous.id, incoming_version_id=incoming.id,
                scope=UpdateScope("FR", ("supplier-new",), evidence=(EvidenceRef(incoming.id, source_row_number=1),)),
            )
            assert outcome.status == "accepted"
            assert outcome.result_hash
            assert session.query(ReconciliationRun).count() == 1
            assert session.query(MaterializedRecord).count() == 1

        with database.transaction() as session:
            replay = ReconciliationService().reconcile(
                session, event_key="reconcile-1", payload={"incoming": incoming.id},
                previous_version_id=previous.id, incoming_version_id=incoming.id,
                scope=UpdateScope("FR", ("supplier-new",), evidence=(EvidenceRef(incoming.id, source_row_number=1),)),
                previous_records=[], incoming_records=[],
            )
            assert replay.event_replayed
            assert replay.status == "accepted"
            assert session.query(ReconciliationRun).count() == 1

        with pytest.raises(IdempotencyConflictError):
            with database.transaction() as session:
                ReconciliationService().reconcile(
                    session, event_key="reconcile-1", payload={"incoming": "different"},
                    previous_version_id=previous.id, incoming_version_id=incoming.id,
                    scope=UpdateScope("FR", ("supplier-new",), evidence=(EvidenceRef(incoming.id, source_row_number=1),)),
                    previous_records=[], incoming_records=[],
                )
    finally:
        database.dispose()


def test_failed_reconciliation_persists_issue_and_does_not_materialize(tmp_path) -> None:
    database = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'failed.db'}"))
    database.create_schema()
    try:
        source = SourceService()
        with database.transaction() as session:
            previous, _, _ = source.accept_version(
                session, content=b"previous", filename="previous.csv", media_type="text/csv",
                market="FR", version_label="v1", scope_key="FR", event_key="source-v1", payload={},
            )
            incoming, _, _ = source.accept_version(
                session, content=b"incoming", filename="incoming.csv", media_type="text/csv",
                market="FR", version_label="v2", scope_key="FR", event_key="source-v2", payload={},
            )
            outcome = ReconciliationService().reconcile(
                session, event_key="reconcile-failed", payload={}, previous_version_id=previous.id,
                incoming_version_id=incoming.id, scope=UpdateScope("FR", (), evidence=()),
                previous_records=[], incoming_records=[],
            )
            assert outcome.status == "needs_review"
            assert session.query(ReconciliationRun).count() == 0
            assert session.query(ReconciliationIssueRecord).count() >= 1
    finally:
        database.dispose()


def test_stale_reconciliation_cannot_overwrite_newer_accepted_version(tmp_path) -> None:
    database = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'stale.db'}"))
    database.create_schema()
    try:
        source = SourceService()
        with database.transaction() as session:
            previous, _, _ = source.accept_version(
                session, content=b"previous", filename="previous.csv", media_type="text/csv",
                market="FR", version_label="v1", scope_key="FR:scope", event_key="source-v1", payload={},
            )
            incoming, _, _ = source.accept_version(
                session, content=b"incoming", filename="incoming.csv", media_type="text/csv",
                market="FR", version_label="v2", scope_key="FR:scope", event_key="source-v2", payload={},
            )
            newer, _, _ = source.accept_version(
                session, content=b"newer", filename="newer.csv", media_type="text/csv",
                market="FR", version_label="v3", scope_key="FR:scope", event_key="source-v3", payload={},
            )
            outcome = ReconciliationService().reconcile(
                session, event_key="stale-reconcile", payload={}, previous_version_id=previous.id,
                incoming_version_id=incoming.id,
                scope=UpdateScope("FR", ("supplier-new",), evidence=(EvidenceRef(incoming.id, source_row_number=1),)),
                previous_records=[], incoming_records=[],
            )
            assert outcome.status == "needs_review"
            assert any(issue.code == "concurrent_version_change" for issue in outcome.issues)
            assert newer.status == SourceStatus.ACCEPTED.value
            assert session.query(ReconciliationRun).count() == 0
    finally:
        database.dispose()

"""Isolated Phase Two persistence tests."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db.models import RecommendationStatus, SourceRecord, SourceStatus
from app.db.session import create_database
from app.persistence import (ApprovalError, EventRepository, IdempotencyConflictError,
                              SourceService, StateTransitionError, ReviewRepository, sha256_bytes)


@pytest.fixture
def database(tmp_path):
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'test.db'}"))
    db.create_schema()
    yield db
    db.dispose()


def test_schema_has_phase_two_tables_and_indexes(database) -> None:
    inspector = inspect(database.engine)
    tables = set(inspector.get_table_names())
    assert {"source_files", "source_versions", "source_records", "workflow_events",
            "recommendations", "evidence_links", "corrections", "approvals"} <= tables
    assert any(index["name"] == "ix_source_versions_scope_status"
               for index in inspector.get_indexes("source_versions"))


def test_source_hash_lineage_records_and_replay(database) -> None:
    service = SourceService()
    payload = {"market": "FR", "version": "v1"}
    records = [{"record_key": "supplier-a:1", "source_row_number": 4,
                "raw_values_json": {"Supplier": "A", "Amount": "10"}, "supplier": "A"}]
    with database.transaction() as session:
        version, event, replayed = service.accept_version(
            session, content=b"same-bytes", filename="fr.csv", media_type="text/csv",
            market="FR", version_label="v1", scope_key="FR", event_key="evt-1",
            payload=payload, records=records)
        assert not replayed and version.status == SourceStatus.ACCEPTED.value
        assert len(service.sources.get_records_for_version(session, version.id)) == 1
    with database.transaction() as session:
        same_version, same_event, replayed = service.accept_version(
            session, content=b"same-bytes", filename="fr.csv", media_type="text/csv",
            market="FR", version_label="v1", scope_key="FR", event_key="evt-1",
            payload=payload, records=records)
        assert replayed and same_version.id == version.id and same_event.id == event.id
    assert sha256_bytes(b"same-bytes") != sha256_bytes(b"other-bytes")


def test_event_conflicting_replay_rolls_back(database) -> None:
    events = EventRepository()
    with database.transaction() as session:
        events.create_or_get_event(session, event_key="evt", payload_hash="a" * 64, event_type="test")
    with pytest.raises(IdempotencyConflictError):
        with database.transaction() as session:
            events.create_or_get_event(session, event_key="evt", payload_hash="b" * 64, event_type="test")


def test_invalid_event_transition_and_orphan_record_rejected(database) -> None:
    events = EventRepository()
    with pytest.raises(StateTransitionError):
        with database.transaction() as session:
            result = events.create_or_get_event(session, event_key="evt", payload_hash="a", event_type="test")
            events.replace_event_status(result.event, "completed")  # type: ignore[arg-type]
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.add(SourceRecord(source_version_id="missing", record_key="r", source_row_number=1,
                                     raw_values_json={}))
            session.flush()


def test_approved_recommendation_is_not_modified_in_place_and_stale_cannot_approve(database) -> None:
    review = ReviewRepository()
    with database.transaction() as session:
        service = SourceService()
        version, _, _ = service.accept_version(session, content=b"x", filename="x.csv", media_type="text/csv",
                                               market="FR", version_label="v1", scope_key="FR", event_key="e",
                                               payload={})
        recommendation = review.create_recommendation(session, source_version_id=version.id,
                                                       recommendation_key="supplier-a", status="draft",
                                                       facts_json={}, explanation_json={}, calculation_hash="h")
        review.create_approval(session, recommendation_id=recommendation.id, decision="approved",
                               reviewer_id="placeholder", reason="checked", calculation_hash="h")
        assert recommendation.status == RecommendationStatus.APPROVED.value
        review.mark_recommendations_stale(session, version.id)
        with pytest.raises(ApprovalError):
            review.create_approval(session, recommendation_id=recommendation.id, decision="approved",
                                   reviewer_id="placeholder", reason="again", calculation_hash="h")

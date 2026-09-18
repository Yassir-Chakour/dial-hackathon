"""Typed persistence services and stable domain errors for Phase Two."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Approval, Correction, EventStatus, EvidenceLink, Recommendation, RecommendationStatus,
    SourceFile, SourceRecord, SourceStatus, SourceVersion, WorkflowEvent, now_utc,
)
from app.storage import PrivateObjectStore


class PersistenceError(Exception):
    """Base error for storage/domain operations."""


class StateTransitionError(PersistenceError):
    pass


class IdempotencyConflictError(PersistenceError):
    pass


class ApprovalError(PersistenceError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EventResult:
    event: WorkflowEvent
    replayed: bool


class SourceRepository:
    def __init__(self, storage: PrivateObjectStore | None = None) -> None:
        self.storage: PrivateObjectStore | None = storage
        if storage is not None:
            return
        from app.config import get_settings

        settings = get_settings()
        self.storage = (
            PrivateObjectStore(settings.object_storage_dir)
            if settings.source_storage_mode == "object_storage"
            else None
        )

    def find_source_by_hash(self, session: Session, sha256: str, tenant_id: str | None = None) -> SourceFile | None:
        return session.scalar(select(SourceFile).where(SourceFile.sha256 == sha256, SourceFile.tenant_id == tenant_id))

    def create_source_file(self, session: Session, *, content: bytes, filename: str, media_type: str,
                           source_system: str | None = None, tenant_id: str | None = None,
                           metadata: dict[str, Any] | None = None, synthetic: bool = True) -> SourceFile:
        source = SourceFile(original_filename=filename[:256], media_type=media_type[:128], size_bytes=len(content),
                            sha256=sha256_bytes(content), content=None if self.storage else content,
                            source_system=source_system, tenant_id=tenant_id,
                            metadata_json=metadata or {}, synthetic=synthetic)
        if self.storage:
            stored = self.storage.put(content, media_type=media_type[:128])
            source.object_key = stored.object_key
        session.add(source)
        session.flush()
        return source

    def create_source_version(self, session: Session, **kwargs: Any) -> SourceVersion:
        kwargs.setdefault("update_mode", "replacement")
        version = SourceVersion(**kwargs)
        session.add(version)
        session.flush()
        return version

    def get_current_version(self, session: Session, scope_key: str) -> SourceVersion | None:
        return session.scalar(select(SourceVersion).where(SourceVersion.scope_key == scope_key,
                                                          SourceVersion.status == SourceStatus.ACCEPTED.value)
                              .order_by(SourceVersion.created_at.desc()))

    def insert_source_records(self, session: Session, version_id: str, records: list[dict[str, Any]]) -> list[SourceRecord]:
        result = []
        for values in records:
            record = SourceRecord(source_version_id=version_id, **values)
            session.add(record)
            result.append(record)
        session.flush()
        return result

    def get_records_for_version(self, session: Session, version_id: str) -> list[SourceRecord]:
        return list(session.scalars(select(SourceRecord).where(SourceRecord.source_version_id == version_id)
                                  .order_by(SourceRecord.source_row_number)))


class EventRepository:
    def create_or_get_event(self, session: Session, *, event_key: str, payload_hash: str,
                            event_type: str, tenant_id: str | None = None, **kwargs: Any) -> EventResult:
        existing = session.scalar(select(WorkflowEvent).where(WorkflowEvent.event_key == event_key,
                                                               WorkflowEvent.tenant_id == tenant_id))
        if existing:
            if existing.payload_hash != payload_hash:
                raise IdempotencyConflictError("Event key was already used with a different payload.")
            return EventResult(existing, True)
        event = WorkflowEvent(event_key=event_key, payload_hash=payload_hash, event_type=event_type,
                              tenant_id=tenant_id, **kwargs)
        session.add(event)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            existing = session.scalar(select(WorkflowEvent).where(WorkflowEvent.event_key == event_key,
                                                                   WorkflowEvent.tenant_id == tenant_id))
            if existing and existing.payload_hash == payload_hash:
                return EventResult(existing, True)
            raise IdempotencyConflictError("Event key conflicts with an existing event.") from exc
        return EventResult(event, False)

    def replace_event_status(self, event: WorkflowEvent, status: EventStatus, *, error_code: str | None = None,
                             error_summary: str | None = None) -> WorkflowEvent:
        allowed = {
            EventStatus.RECEIVED: {EventStatus.PROCESSING, EventStatus.NEEDS_REVIEW},
            EventStatus.PROCESSING: {EventStatus.COMPLETED, EventStatus.FAILED, EventStatus.NEEDS_REVIEW},
            EventStatus.COMPLETED: set(), EventStatus.FAILED: set(), EventStatus.NEEDS_REVIEW: set(),
        }
        current = EventStatus(event.status)
        if status not in allowed[current]:
            raise StateTransitionError(f"Invalid event transition: {current} -> {status}.")
        event.status = status.value
        event.attempt_count += 1
        if status == EventStatus.PROCESSING:
            event.started_at = now_utc()
        if status in {EventStatus.COMPLETED, EventStatus.FAILED, EventStatus.NEEDS_REVIEW}:
            event.completed_at = now_utc()
        event.error_code, event.error_summary = error_code, error_summary[:512] if error_summary else None
        return event


class ReviewRepository:
    def create_recommendation(self, session: Session, **kwargs: Any) -> Recommendation:
        recommendation = Recommendation(**kwargs)
        session.add(recommendation)
        session.flush()
        return recommendation

    def link_evidence(self, session: Session, **kwargs: Any) -> EvidenceLink:
        link = EvidenceLink(**kwargs)
        session.add(link)
        session.flush()
        return link

    def record_correction(self, session: Session, **kwargs: Any) -> Correction:
        correction = Correction(**kwargs)
        session.add(correction)
        session.flush()
        return correction

    create_correction = record_correction

    def create_approval(self, session: Session, *, recommendation_id: str, decision: str,
                        reviewer_id: str, reason: str, calculation_hash: str) -> Approval:
        recommendation = session.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise ApprovalError("Recommendation does not exist.")
        if recommendation.status in {RecommendationStatus.APPROVED.value, RecommendationStatus.STALE.value, RecommendationStatus.REJECTED.value}:
            raise ApprovalError("Already approved, stale, or rejected recommendations cannot be approved.")
        if recommendation.calculation_hash != calculation_hash:
            raise ApprovalError("Approval hash does not match the recommendation version.")
        if decision not in {"approved", "rejected"}:
            raise ApprovalError("Approval decision must be approved or rejected.")
        recommendation.status = decision
        approval = Approval(recommendation_id=recommendation_id, decision=decision, reviewer_id=reviewer_id,
                            reason=reason[:1000], calculation_hash=calculation_hash)
        session.add(approval)
        session.flush()
        return approval

    def mark_recommendations_stale(self, session: Session, input_version_id: str) -> int:
        recommendations = list(session.scalars(select(Recommendation).where(
            Recommendation.source_version_id == input_version_id,
            Recommendation.status.in_([RecommendationStatus.DRAFT.value, RecommendationStatus.NEEDS_REVIEW.value,
                                       RecommendationStatus.APPROVED.value])
        )))
        for recommendation in recommendations:
            recommendation.status = RecommendationStatus.STALE.value
            recommendation.superseded_at = now_utc()
        return len(recommendations)


class SourceService:
    """Coordinates source/version/event writes in one caller-owned transaction."""

    def __init__(self, sources: SourceRepository | None = None, events: EventRepository | None = None) -> None:
        self.sources = sources or SourceRepository()
        self.events = events or EventRepository()

    def accept_version(self, session: Session, *, content: bytes, filename: str, media_type: str,
                       market: str, version_label: str, scope_key: str, event_key: str,
                       payload: Any, records: list[dict[str, Any]] | None = None,
                       update_mode: str = "initial", tenant_id: str | None = None) -> tuple[SourceVersion, WorkflowEvent, bool]:
        source = self.sources.find_source_by_hash(session, sha256_bytes(content), tenant_id)
        if source is None:
            source = self.sources.create_source_file(session, content=content, filename=filename,
                                                     media_type=media_type, tenant_id=tenant_id)
        event_result = self.events.create_or_get_event(session, event_key=event_key,
                                                       payload_hash=sha256_payload(payload),
                                                       event_type="source.accept", tenant_id=tenant_id,
                                                       source_file_id=source.id)
        if event_result.replayed and event_result.event.source_version_id:
            version = session.get(SourceVersion, event_result.event.source_version_id)
            if version is None:
                raise PersistenceError("Idempotent event points to a missing source version.")
            return version, event_result.event, True
        version = self.sources.create_source_version(session, source_file_id=source.id, tenant_id=tenant_id,
                                                     market=market, version_label=version_label,
                                                     update_mode=update_mode, scope_key=scope_key)
        if records:
            self.sources.insert_source_records(session, version.id, records)
        event_result.event.source_version_id = version.id
        self.events.replace_event_status(event_result.event, EventStatus.PROCESSING)
        self.events.replace_event_status(event_result.event, EventStatus.COMPLETED)
        version.status = SourceStatus.ACCEPTED.value
        version.accepted_at = now_utc()
        return version, event_result.event, False

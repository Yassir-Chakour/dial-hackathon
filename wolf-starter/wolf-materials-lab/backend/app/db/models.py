"""Storage models for source evidence, workflow state and review decisions."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class SourceStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class EventStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class RecommendationStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    SUPERSEDED = "superseded"


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes | None] = mapped_column(nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    retention_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synthetic: Mapped[bool] = mapped_column(default=True, nullable=False)
    versions: Mapped[list["SourceVersion"]] = relationship(back_populates="source_file")

    __table_args__ = (
        UniqueConstraint("tenant_id", "sha256", name="uq_source_tenant_hash"),
        CheckConstraint("size_bytes >= 0", name="ck_source_size_nonnegative"),
    )


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (
        Index("ix_source_versions_scope_status", "scope_key", "status"),
        Index("ix_source_versions_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"), nullable=True)
    update_mode: Mapped[str] = mapped_column(String(32), default="replacement", nullable=False)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=SourceStatus.RECEIVED.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_file: Mapped[SourceFile] = relationship(back_populates="versions")
    records: Mapped[list["SourceRecord"]] = relationship(back_populates="source_version", cascade="all, delete-orphan")


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("source_version_id", "record_key", name="uq_record_version_key"),
        Index("ix_source_records_record_key", "record_key"),
        CheckConstraint("source_row_number >= 1", name="ck_record_row_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.id"), nullable=False)
    record_key: Mapped[str] = mapped_column(String(256), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sheet: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw_values_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(256), nullable=True)
    product: Mapped[str | None] = mapped_column(String(256), nullable=True)
    record_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    record_kind: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), default="valid", nullable=False)
    validation_errors_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    source_version: Mapped[SourceVersion] = relationship(back_populates="records")


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_key", name="uq_event_tenant_key"), Index("ix_events_status", "status"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_key: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("source_files.id"), nullable=True)
    source_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=EventStatus.RECEIVED.value, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("source_version_id", "recommendation_key", name="uq_recommendation_version_key"), Index("ix_recommendations_status", "status"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.id"), nullable=False)
    input_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("decision_input_snapshots.id"), nullable=True)
    recommendation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RecommendationStatus.DRAFT.value, nullable=False)
    facts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    calculation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    recommendation_key_stable: Mapped[str | None] = mapped_column(String(256), nullable=True)
    blocking_issue_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_complete: Mapped[bool] = mapped_column(default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_recommendation_id: Mapped[str | None] = mapped_column(ForeignKey("recommendations.id"), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    __table_args__ = (UniqueConstraint("recommendation_id", "source_record_id", "relation", name="uq_evidence_link"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(128), default="anonymous-placeholder", nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    correction_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    validation_type: Mapped[str] = mapped_column(String(64), default="schema", nullable=False)
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="accepted", nullable=False)
    requires_reconciliation: Mapped[bool] = mapped_column(default=False, nullable=False)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_recommendation", "recommendation_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(128), default="anonymous-placeholder", nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    calculation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    input_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("decision_input_snapshots.id"), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), default="phase-six-v1", nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DecisionInputSnapshotRow(Base):
    """Immutable canonical inputs for a recommendation."""

    __tablename__ = "decision_input_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reconciliation_version_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_runs.id"), nullable=False)
    source_version_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    change_set_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    corrections_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    assumptions_json: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    product_key: Mapped[str] = mapped_column(String(256), nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(256), nullable=True)
    market: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    input_record_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class MockAction(Base):
    __tablename__ = "mock_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class ReconciliationRun(Base):
    """Immutable audit record for one accepted or rejected reconciliation attempt."""

    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_reconciliation_run_event"),
        UniqueConstraint("result_hash", name="uq_reconciliation_run_hash"),
        Index("ix_reconciliation_runs_scope_status", "scope_key", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("workflow_events.id"), nullable=False)
    previous_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.id"), nullable=False)
    incoming_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.id"), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"), nullable=True)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    totals_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    changes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class MaterializedRecord(Base):
    """Current snapshot row; historical source rows are never mutated or deleted."""

    __tablename__ = "materialized_records"
    __table_args__ = (UniqueConstraint("reconciliation_run_id", "record_key", name="uq_materialized_run_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reconciliation_run_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_runs.id"), nullable=False)
    record_key: Mapped[str] = mapped_column(String(256), nullable=False)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), nullable=False)
    prior_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"), nullable=True)
    lineage: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)


class ReconciliationIssueRecord(Base):
    """Safe, structured failure/review evidence without copying raw source rows."""

    __tablename__ = "reconciliation_issues"
    __table_args__ = (Index("ix_reconciliation_issues_event", "event_id", "severity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("workflow_events.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class WorkflowRun(Base):
    """Execution run for an orchestrated agent workflow."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_workflow_run_event"),
        Index("ix_workflow_runs_status", "status"),
        Index("ix_workflow_runs_fingerprint", "input_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("workflow_events.id"), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("source_files.id"), nullable=True)
    source_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"), nullable=True)
    previous_version_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False
    )

    checkpoints: Mapped[list["WorkflowCheckpoint"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="WorkflowCheckpoint.step_index"
    )


class WorkflowCheckpoint(Base):
    """Immutable state snapshot captured at a workflow stage or review pause."""

    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        UniqueConstraint("run_id", "step_index", name="uq_checkpoint_run_step"),
        Index("ix_workflow_checkpoints_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    run: Mapped[WorkflowRun] = relationship(back_populates="checkpoints")

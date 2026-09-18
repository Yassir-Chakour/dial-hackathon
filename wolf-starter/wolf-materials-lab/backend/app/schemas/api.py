"""Typed Pydantic request and response contracts for the Phase Seven REST API."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class PageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    next_cursor: str | None = None
    limit: int = 20
    total: int | None = None


# --- Source Schemas ---


class SourceUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    sha256: str
    size_bytes: int
    media_type: str
    received_at: str
    synthetic: bool = True
    workflow_run_id: str | None = None


class SourceDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    received_at: str
    version_count: int


class SourceVersionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version_label: str
    market: str
    status: str
    update_mode: str
    parent_version_id: str | None = None
    created_at: str


class ProcessVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str | None = None


# --- Workflow Schemas ---


class WorkflowRunDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    event_id: str
    market: str
    stage: str
    status: str
    workflow_version: str
    source_file_id: str | None = None
    source_version_id: str | None = None
    previous_version_id: str | None = None
    reconciliation_result_id: str | None = None
    recommendation_draft: dict[str, Any] | None = None
    review_request: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None
    issues: list[dict[str, Any]] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)


class ResumeRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1)
    correction_payload: dict[str, Any] | None = None


# --- Recommendation Schemas ---


class RecommendationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recommendation_key: str
    source_version_id: str
    status: str
    calculation_hash: str
    created_at: str
    superseded_at: str | None = None


class RecommendationDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recommendation_key: str
    source_version_id: str
    status: str
    facts: dict[str, Any]
    explanation: dict[str, Any]
    calculation_hash: str
    created_at: str
    allowed_actions: list[str] = Field(default_factory=list)


class RecommendationChangesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendation_id: str
    scope: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)
    added: list[dict[str, Any]] = Field(default_factory=list)
    replaced: list[dict[str, Any]] = Field(default_factory=list)
    removed_from_current: list[dict[str, Any]] = Field(default_factory=list)
    preserved: list[dict[str, Any]] = Field(default_factory=list)


class RecommendationHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: str
    event_type: str
    status: str
    calculation_hash: str
    timestamp: str
    note: str | None = None


class ApproveRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calculation_hash: str = Field(min_length=1)
    reason: str = Field(default="Approved by reviewer", max_length=1000)
    idempotency_key: str | None = None


class RejectRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)
    calculation_hash: str | None = None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str
    recommendation_id: str
    decision: str
    status: str
    reviewer_id: str
    calculation_hash: str
    timestamp: str


class RevokeApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)


# --- Correction Schemas ---


class SubmitCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_record_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1, max_length=128)
    original_value: str | None = None
    corrected_value: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=1000)


class CorrectionDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    source_record_id: str
    field_name: str
    original_value: str | None = None
    corrected_value: str
    reviewer_id: str
    reason: str
    created_at: str


# --- Evidence and Lineage Schemas ---


class EvidenceDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recommendation_id: str
    source_record_id: str
    source_file_id: str
    relation: str
    created_at: str


class RecordLineageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str
    record_key: str
    version_id: str
    source_row_number: int
    lineage: str
    prior_record_id: str | None = None


# --- Replay Schemas ---


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1)
    mode: str = Field(default="dry_run", pattern=r"^(dry_run|apply_if_safe)$")


class ReplayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_event_id: str
    replayed: bool
    mode: str
    identical_result: bool
    original_result_hash: str
    replay_result_hash: str
    status: str


# --- Review Queue and Exceptions Schemas ---


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    checkpoint_id: str
    stage: str
    status: str
    blocking_issues: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    created_at: str


class ResolveReviewQueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1)
    correction: dict[str, Any] | None = None


class ExceptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    event_id: str
    code: str
    severity: str
    message: str
    created_at: str

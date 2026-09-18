"""API-safe Phase Six decision schemas; raw source rows are intentionally absent."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionInputSnapshotSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reconciliation_version_id: str = Field(min_length=1, max_length=64)
    source_version_ids: list[str] = Field(min_length=1, max_length=100)
    change_set_id: str | None = Field(default=None, max_length=256)
    calculation_version: str = Field(default="phase-six-v1", max_length=32)
    input_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime


class RecommendationDecisionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recommendation_key: str
    status: Literal["draft", "needs_review", "approved", "rejected", "stale", "superseded"]
    input_hash: str
    result_hash: str
    evidence_complete: bool
    blocking_issue_ids: list[str] = Field(default_factory=list, max_length=100)
    created_at: datetime


class ApprovalRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendation_id: str = Field(min_length=1, max_length=64)
    result_hash: str = Field(min_length=64, max_length=64)
    input_hash: str = Field(min_length=64, max_length=64)
    reviewer_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=128)

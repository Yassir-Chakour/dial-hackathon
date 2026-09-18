"""Pydantic schemas for workflow service request and response boundaries."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class StartWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_file_id: str = Field(min_length=1)
    event_key: str = Field(min_length=1)
    market: str = Field(default="FR", min_length=2, max_length=16)
    previous_version_id: str | None = None
    tenant_id: str | None = None


class ResumeWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    correction_payload: dict[str, Any] | None = None


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    event_id: str
    market: str
    stage: str
    status: str
    workflow_version: str
    source_version_id: str | None = None
    reconciliation_result_id: str | None = None
    recommendation_draft: dict[str, Any] | None = None
    review_request: dict[str, Any] | None = None
    issues: list[dict[str, Any]] = Field(default_factory=list)
    replayed: bool = False

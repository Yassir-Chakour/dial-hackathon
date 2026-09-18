"""Typed Pydantic tool contracts for agent workflow execution."""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.reconciliation.contracts import UpdateScope


class InspectSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_file_id: str = Field(min_length=1)
    tenant_id: str | None = None


class InspectSourceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    representation: str
    total_rows: int
    candidate_headers: list[str] = Field(default_factory=list)
    duplicate_headers: list[str] = Field(default_factory=list)
    preamble_rows: int = 0
    warnings: list[str] = Field(default_factory=list)


class IngestSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_file_id: str = Field(min_length=1)
    event_key: str = Field(min_length=1)
    market: str = "FR"
    tenant_id: str | None = None


class IngestSourceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_version_id: str
    result_hash: str
    total_rows: int
    record_count: int
    valid_count: int
    review_count: int
    detected_scope: dict[str, Any] = Field(default_factory=dict)
    replayed: bool = False


class ReconcileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    previous_version_id: str = Field(min_length=1)
    incoming_version_id: str = Field(min_length=1)
    scope: UpdateScope
    event_key: str = Field(min_length=1)
    tenant_id: str | None = None


class ReconcileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reconciliation_run_id: str
    status: Literal["accepted", "needs_review", "rejected"]
    result_hash: str
    totals: dict[str, Any] = Field(default_factory=dict)
    change_set: dict[str, Any] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    replayed: bool = False


class ImpactAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_set: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)


class ImpactAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changed_records_count: int
    affected_suppliers: list[str] = Field(default_factory=list)
    affected_products: list[str] = Field(default_factory=list)
    old_total: str | None = None
    new_total: str | None = None
    difference: str | None = None
    impact_severity: Literal["low", "medium", "high"] = "low"


class CollectEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_version_id: str = Field(min_length=1)
    change_set: dict[str, Any] = Field(default_factory=dict)


class CollectEvidenceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    citation_count: int
    citations: list[dict[str, Any]] = Field(default_factory=list)
    missing_evidence_count: int = 0

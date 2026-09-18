"""Typed workflow state contracts for Phase Five agent orchestration."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, TypedDict

from app.reconciliation.contracts import UpdateScope

WorkflowStage = Literal[
    "received",
    "inspected",
    "scoped",
    "ingested",
    "reconciled",
    "impacted",
    "drafted",
    "awaiting_review",
    "completed",
    "failed",
    "needs_review",
]

WorkflowStatus = Literal[
    "running",
    "paused",
    "completed",
    "failed",
    "needs_review",
]

WORKFLOW_VERSION = "phase-five-v1.0"


@dataclass(frozen=True)
class WorkflowBudgets:
    step_limit: int = 20
    current_steps: int = 0
    max_tool_calls: int = 10
    current_tool_calls: int = 0
    max_model_calls: int = 5
    current_model_calls: int = 0
    max_duration_seconds: float = 60.0


@dataclass(frozen=True)
class WorkflowIssue:
    code: str
    message: str
    severity: Literal["error", "warning", "info"] = "error"
    node: str = ""
    evidence: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ReviewRequest:
    run_id: str
    checkpoint_id: str
    blocking_issue_ids: tuple[str, ...] = ()
    affected_record_ids: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    allowed_actions: tuple[str, ...] = (
        "accept_scope",
        "correct_record",
        "reject_update",
        "continue_to_approval_phase",
    )
    required: bool = True


@dataclass(frozen=True)
class ImpactSummary:
    changed_records_count: int
    affected_supplier_ids: tuple[str, ...] = ()
    affected_product_ids: tuple[str, ...] = ()
    old_total: Decimal | None = None
    new_total: Decimal | None = None
    difference: Decimal | None = None
    citations: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RecommendationDraft:
    recommendation_key: str
    supplier_id: str
    facts: dict[str, Any] = field(default_factory=dict)
    savings_estimate: Decimal | None = None
    explanation: str = ""
    confidence: Literal["high", "medium", "low"] = "high"
    citation_refs: tuple[dict[str, Any], ...] = ()


class WorkflowState(TypedDict):
    run_id: str
    event_id: str
    tenant_id: str | None
    market: str
    source_file_id: str
    source_version_id: str | None
    previous_version_id: str | None
    parser_version: str | None
    workflow_version: str
    stage: WorkflowStage
    status: WorkflowStatus
    scope: UpdateScope | None
    ingestion_result_id: str | None
    reconciliation_result_id: str | None
    impact_summary: ImpactSummary | None
    recommendation_draft: RecommendationDraft | None
    evidence_refs: list[dict[str, Any]]
    issues: list[WorkflowIssue]
    review_request: ReviewRequest | None
    budgets: WorkflowBudgets
    idempotency_key: str
    history: list[str]

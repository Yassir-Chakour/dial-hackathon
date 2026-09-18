"""Unit tests for typed workflow state contracts and budgets."""

from decimal import Decimal

from app.workflows.state import (
    WORKFLOW_VERSION,
    ImpactSummary,
    RecommendationDraft,
    ReviewRequest,
    WorkflowBudgets,
    WorkflowIssue,
    WorkflowState,
)


def test_workflow_state_initialization() -> None:
    budgets = WorkflowBudgets()
    state: WorkflowState = {
        "run_id": "run-001",
        "event_id": "evt-001",
        "tenant_id": None,
        "market": "FR",
        "source_file_id": "file-001",
        "source_version_id": None,
        "previous_version_id": "prev-001",
        "parser_version": "1.0",
        "workflow_version": WORKFLOW_VERSION,
        "stage": "received",
        "status": "running",
        "scope": None,
        "ingestion_result_id": None,
        "reconciliation_result_id": None,
        "impact_summary": None,
        "recommendation_draft": None,
        "evidence_refs": [],
        "issues": [],
        "review_request": None,
        "budgets": budgets,
        "idempotency_key": "idemp-001",
        "history": [],
    }

    assert state["run_id"] == "run-001"
    assert state["stage"] == "received"
    assert state["budgets"].step_limit == 20
    assert state["budgets"].current_steps == 0


def test_workflow_models() -> None:
    issue = WorkflowIssue(code="test_err", message="Something broke", severity="error", node="intake")
    assert issue.code == "test_err"

    req = ReviewRequest(run_id="run-1", checkpoint_id="chk-1", blocking_issue_ids=("test_err",))
    assert "accept_scope" in req.allowed_actions
    assert req.required

    impact = ImpactSummary(
        changed_records_count=5,
        old_total=Decimal("100.00"),
        new_total=Decimal("80.00"),
        difference=Decimal("-20.00"),
    )
    assert impact.difference == Decimal("-20.00")

    draft = RecommendationDraft(
        recommendation_key="rec-1",
        supplier_id="sup-aster",
        facts={"savings": "20.00"},
        savings_estimate=Decimal("20.00"),
    )
    assert draft.savings_estimate == Decimal("20.00")

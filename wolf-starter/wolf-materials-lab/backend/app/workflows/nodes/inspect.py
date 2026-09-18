"""Inspect node: verifies file format, row counts, and header structures."""

from typing import Any
from sqlalchemy.orm import Session

from app.workflows.policies import enforce_budget, validate_transition
from app.workflows.state import WorkflowIssue, WorkflowState
from app.workflows.tools.contracts import InspectSourceInput
from app.workflows.tools.ingestion_tools import inspect_source_tool


def inspect_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Inspect structure and candidate headers without database mutation."""
    budgets = enforce_budget(state["budgets"], operation="step")
    budgets = enforce_budget(budgets, operation="tool")

    try:
        inspection = inspect_source_tool(
            session,
            InspectSourceInput(
                source_file_id=state["source_file_id"],
                tenant_id=state["tenant_id"],
            ),
        )
    except Exception as exc:
        return {
            "stage": "failed",
            "status": "failed",
            "issues": state["issues"] + [
                WorkflowIssue(
                    code="inspection_failed",
                    message=f"Inspection failed: {exc}",
                    severity="error",
                    node="inspect",
                )
            ],
            "budgets": budgets,
            "history": state["history"] + ["inspect"],
        }

    if inspection.total_rows < 1:
        return {
            "stage": "failed",
            "status": "failed",
            "issues": state["issues"] + [
                WorkflowIssue(
                    code="empty_source_file",
                    message="Source file contains no data rows.",
                    severity="error",
                    node="inspect",
                )
            ],
            "budgets": budgets,
            "history": state["history"] + ["inspect"],
        }

    validate_transition(state["stage"], "scoped")
    return {
        "stage": "scoped",
        "status": "running",
        "budgets": budgets,
        "history": state["history"] + ["inspect"],
    }

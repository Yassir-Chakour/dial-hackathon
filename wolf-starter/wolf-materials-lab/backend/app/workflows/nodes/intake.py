"""Intake node: initializes and validates input parameters for the workflow run."""

from typing import Any
from sqlalchemy.orm import Session

from app.db.models import SourceFile
from app.workflows.policies import enforce_budget, validate_transition
from app.workflows.state import WorkflowIssue, WorkflowState


def intake_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Validate intake parameters, source file existence, and enforce initial budgets."""
    budgets = enforce_budget(state["budgets"], operation="step")

    source_file = session.get(SourceFile, state["source_file_id"])
    if source_file is None:
        return {
            "stage": "failed",
            "status": "failed",
            "issues": state["issues"] + [
                WorkflowIssue(
                    code="source_file_not_found",
                    message=f"Source file {state['source_file_id']} does not exist.",
                    severity="error",
                    node="intake",
                )
            ],
            "budgets": budgets,
            "history": state["history"] + ["intake"],
        }

    validate_transition(state["stage"], "inspected")
    return {
        "stage": "inspected",
        "status": "running",
        "budgets": budgets,
        "history": state["history"] + ["intake"],
    }

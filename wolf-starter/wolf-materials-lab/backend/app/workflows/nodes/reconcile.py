"""Reconciliation node: executes pure supplier-subset version reconciliation."""

from typing import Any
from sqlalchemy.orm import Session

from app.persistence import SourceRepository
from app.workflows.policies import enforce_budget, validate_transition
from app.workflows.state import WorkflowIssue, WorkflowState
from app.workflows.tools.contracts import ReconcileInput
from app.workflows.tools.reconciliation_tools import reconcile_tool


def reconcile_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Execute deterministic Phase Four reconciliation and record change sets."""
    budgets = enforce_budget(state["budgets"], operation="step")
    budgets = enforce_budget(budgets, operation="tool")

    incoming_id = state.get("source_version_id")
    if not incoming_id:
        return {
            "stage": "failed",
            "status": "failed",
            "issues": state["issues"] + [
                WorkflowIssue(
                    code="missing_incoming_version",
                    message="No incoming source version available for reconciliation.",
                    severity="error",
                    node="reconcile",
                )
            ],
            "budgets": budgets,
            "history": state["history"] + ["reconcile"],
        }

    previous_id = state.get("previous_version_id")
    if not previous_id:
        # Find current active version for market
        source_repo = SourceRepository()
        curr = source_repo.get_current_version(
            session,
            state["market"],
            exclude_version_id=incoming_id,
        )
        if curr:
            previous_id = curr.id
        else:
            return {
                "stage": "needs_review",
                "status": "needs_review",
                "issues": state["issues"] + [
                    WorkflowIssue(
                        code="missing_previous_version",
                        message="Replacement update requires an accepted previous version.",
                        severity="error",
                        node="reconcile",
                    )
                ],
                "budgets": budgets,
                "history": state["history"] + ["reconcile"],
            }

    scope = state.get("scope")
    if not scope:
        return {
            "stage": "needs_review",
            "status": "needs_review",
            "issues": state["issues"] + [
                WorkflowIssue(
                    code="missing_update_scope",
                    message="Reconciliation requires a validated update scope.",
                    severity="error",
                    node="reconcile",
                )
            ],
            "budgets": budgets,
            "history": state["history"] + ["reconcile"],
        }

    outcome = reconcile_tool(
        session,
        ReconcileInput(
            previous_version_id=previous_id,
            incoming_version_id=incoming_id,
            scope=scope,
            event_key=f"reconcile:{state['event_id']}",
            tenant_id=state["tenant_id"],
        ),
    )

    if outcome.status != "accepted":
        issue_objects = [
            WorkflowIssue(
                code=str(iss.get("code", "reconciliation_issue")),
                message=str(iss.get("message", "Reconciliation flagged an issue")),
                severity="error" if iss.get("severity") == "error" else "warning",
                node="reconcile",
            )
            for iss in outcome.issues
        ]
        return {
            "stage": "needs_review",
            "status": "needs_review",
            "previous_version_id": previous_id,
            "reconciliation_result_id": outcome.result_hash,
            "issues": state["issues"] + issue_objects,
            "budgets": budgets,
            "history": state["history"] + ["reconcile"],
        }

    validate_transition(state["stage"], "impacted")
    return {
        "stage": "impacted",
        "status": "running",
        "previous_version_id": previous_id,
        "reconciliation_result_id": outcome.result_hash,
        "budgets": budgets,
        "history": state["history"] + ["reconcile"],
    }

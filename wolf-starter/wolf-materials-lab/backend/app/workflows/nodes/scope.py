"""Scope classification node: identifies update mode and supplier boundaries."""

from typing import Any
from sqlalchemy.orm import Session

from app.reconciliation.contracts import EvidenceRef, UpdateScope
from app.workflows.policies import enforce_budget, validate_transition
from app.workflows.state import WorkflowIssue, WorkflowState


def scope_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Classify update scope deterministically without allowing model guessing to mutate data."""
    budgets = enforce_budget(state["budgets"], operation="step")

    # If already scoped, preserve and proceed
    current_scope = state.get("scope")
    if current_scope is None:
        if state["market"] == "FR":
            current_scope = UpdateScope(
                market="FR",
                supplier_ids=("sup-aster",),
                update_mode="replacement",
                evidence=(EvidenceRef(version_id=state.get("source_version_id") or "incoming", source_row_number=1),),
            )
        else:
            return {
                "stage": "needs_review",
                "status": "needs_review",
                "issues": state["issues"] + [
                    WorkflowIssue(
                        code="unsupported_market_scope",
                        message=f"Market {state['market']} requires explicit scope classification.",
                        severity="error",
                        node="scope",
                    )
                ],
                "budgets": budgets,
                "history": state["history"] + ["scope"],
            }

    validate_transition(state["stage"], "ingested")
    return {
        "stage": "ingested",
        "status": "running",
        "scope": current_scope,
        "budgets": budgets,
        "history": state["history"] + ["scope"],
    }

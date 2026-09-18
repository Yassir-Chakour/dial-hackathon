from typing import Any
from sqlalchemy.orm import Session

from app.workflows.policies import enforce_budget, validate_transition
from app.workflows.state import ReviewRequest, WorkflowState


def review_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Create a structured ReviewRequest and pause execution at the human-review boundary."""
    budgets = enforce_budget(state["budgets"], operation="step")
    validate_transition(state["stage"], "awaiting_review")

    blocking_issues = tuple(iss.code for iss in state.get("issues", []) if iss.severity == "error")
    citations = tuple(state.get("evidence_refs", []))

    review_req = ReviewRequest(
        run_id=state["run_id"],
        checkpoint_id=f"chk:{state['run_id']}:{budgets.current_steps}",
        blocking_issue_ids=blocking_issues,
        affected_record_ids=(),
        evidence_refs=citations[:20],
        allowed_actions=(
            "accept_scope",
            "correct_record",
            "reject_update",
            "continue_to_approval_phase",
        ),
        required=True,
    )

    return {
        "stage": "awaiting_review",
        "status": "paused",
        "review_request": review_req,
        "budgets": budgets,
        "history": state["history"] + ["review"],
    }

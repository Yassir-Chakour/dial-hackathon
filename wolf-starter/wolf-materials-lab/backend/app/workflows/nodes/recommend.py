"""Recommendation drafting node: builds a draft procurement recommendation from validated facts."""

from typing import Any
from sqlalchemy.orm import Session

from app.workflows.policies import defend_prompt_injection, enforce_budget
from app.workflows.state import RecommendationDraft, WorkflowState


def recommend_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Draft a procurement recommendation citing only validated backend facts."""
    budgets = enforce_budget(state["budgets"], operation="step")

    impact = state.get("impact_summary")
    scope = state.get("scope")
    supplier_id = scope.supplier_ids[0] if scope and scope.supplier_ids else "unknown"

    savings = None
    if impact and impact.difference is not None:
        savings = -impact.difference if impact.difference < 0 else None

    # Explanation text constructed safely from validated facts
    diff_text = f"{impact.difference} EUR" if impact and impact.difference is not None else "undetermined"
    raw_explanation = (
        f"France market supplier {supplier_id} replacement update processed. "
        f"Total spend delta: {diff_text}. "
        f"Changed records: {impact.changed_records_count if impact else 0}."
    )
    explanation = defend_prompt_injection(raw_explanation)

    citations = tuple(state.get("evidence_refs", []))

    draft = RecommendationDraft(
        recommendation_key=f"rec:{state['market']}:{supplier_id}:{state['event_id']}",
        supplier_id=supplier_id,
        facts={
            "market": state["market"],
            "supplier_id": supplier_id,
            "changed_records": impact.changed_records_count if impact else 0,
            "old_total": str(impact.old_total) if impact and impact.old_total else None,
            "new_total": str(impact.new_total) if impact and impact.new_total else None,
        },
        savings_estimate=savings,
        explanation=explanation,
        confidence="high",
        citation_refs=citations[:20],
    )

    return {
        "stage": "drafted",
        "status": "running",
        "recommendation_draft": draft,
        "budgets": budgets,
        "history": state["history"] + ["recommend"],
    }

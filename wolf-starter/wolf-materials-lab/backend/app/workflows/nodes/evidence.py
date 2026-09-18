"""Evidence collection node: aggregates and audits source row citations."""

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ReconciliationRun
from app.workflows.policies import enforce_budget
from app.workflows.state import WorkflowState
from app.workflows.tools.contracts import CollectEvidenceInput
from app.workflows.tools.evidence_tools import collect_evidence_tool


def evidence_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Collect source file/row references for all changed records."""
    budgets = enforce_budget(state["budgets"], operation="step")
    budgets = enforce_budget(budgets, operation="tool")

    run_hash = state.get("reconciliation_result_id")
    changes_data: dict[str, Any] = {}
    if run_hash:
        run = session.scalar(select(ReconciliationRun).where(ReconciliationRun.result_hash == run_hash))
        if run:
            changes_data = run.changes_json or {}

    version_id = state.get("source_version_id") or "unknown"
    collected = collect_evidence_tool(
        session,
        CollectEvidenceInput(source_version_id=version_id, change_set=changes_data),
    )

    return {
        "evidence_refs": state["evidence_refs"] + collected.citations,
        "budgets": budgets,
        "history": state["history"] + ["evidence"],
    }

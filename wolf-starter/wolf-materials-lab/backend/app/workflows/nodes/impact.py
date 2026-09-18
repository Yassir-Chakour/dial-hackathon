"""Impact analysis node: computes spend differences and affected product categories."""

from decimal import Decimal
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ReconciliationRun
from app.workflows.policies import enforce_budget, validate_transition
from app.workflows.state import ImpactSummary, WorkflowState
from app.workflows.tools.contracts import ImpactAnalysisInput
from app.workflows.tools.evidence_tools import impact_analysis_tool


def impact_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Identify changes to procurement spend and affected catalog items."""
    budgets = enforce_budget(state["budgets"], operation="step")
    budgets = enforce_budget(budgets, operation="tool")

    run_hash = state.get("reconciliation_result_id")
    changes_data: dict[str, Any] = {}
    totals_data: dict[str, Any] = {}

    if run_hash:
        run = session.scalar(select(ReconciliationRun).where(ReconciliationRun.result_hash == run_hash))
        if run:
            changes_data = run.changes_json or {}
            totals_data = run.totals_json or {}

    analysis = impact_analysis_tool(
        ImpactAnalysisInput(change_set=changes_data, totals=totals_data)
    )

    old_tot = Decimal(analysis.old_total) if analysis.old_total else None
    new_tot = Decimal(analysis.new_total) if analysis.new_total else None
    diff = Decimal(analysis.difference) if analysis.difference else None

    impact_summary = ImpactSummary(
        changed_records_count=analysis.changed_records_count,
        affected_supplier_ids=tuple(analysis.affected_suppliers),
        affected_product_ids=tuple(analysis.affected_products),
        old_total=old_tot,
        new_total=new_tot,
        difference=diff,
    )

    validate_transition(state["stage"], "drafted")
    return {
        "stage": "drafted",
        "status": "running",
        "impact_summary": impact_summary,
        "budgets": budgets,
        "history": state["history"] + ["impact"],
    }

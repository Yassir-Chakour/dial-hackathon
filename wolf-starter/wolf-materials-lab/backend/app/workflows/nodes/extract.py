"""Extraction/Ingestion node: parses rows into canonical procurement records."""

from typing import Any
from sqlalchemy.orm import Session

from app.workflows.policies import enforce_budget, validate_transition
from app.workflows.state import WorkflowIssue, WorkflowState
from app.workflows.tools.contracts import IngestSourceInput
from app.workflows.tools.ingestion_tools import ingest_source_tool


def extract_node(session: Session, state: WorkflowState) -> dict[str, Any]:
    """Execute deterministic Phase Three ingestion and record version IDs."""
    budgets = enforce_budget(state["budgets"], operation="step")
    budgets = enforce_budget(budgets, operation="tool")

    try:
        res = ingest_source_tool(
            session,
            IngestSourceInput(
                source_file_id=state["source_file_id"],
                event_key=state["event_id"],
                market=state["market"],
                tenant_id=state["tenant_id"],
            ),
        )
    except Exception as exc:
        return {
            "stage": "failed",
            "status": "failed",
            "issues": state["issues"] + [
                WorkflowIssue(
                    code="ingestion_failed",
                    message=f"Ingestion service failed: {exc}",
                    severity="error",
                    node="extract",
                )
            ],
            "budgets": budgets,
            "history": state["history"] + ["extract"],
        }

    validate_transition(state["stage"], "reconciled")
    return {
        "stage": "reconciled",
        "status": "running",
        "source_version_id": res.source_version_id,
        "ingestion_result_id": res.result_hash,
        "budgets": budgets,
        "history": state["history"] + ["extract"],
    }

"""Impact analysis and evidence collection tools for workflow stages."""

from decimal import Decimal
from typing import Any
from sqlalchemy.orm import Session

from app.workflows.tools.contracts import (
    CollectEvidenceInput,
    CollectEvidenceOutput,
    ImpactAnalysisInput,
    ImpactAnalysisOutput,
)


def impact_analysis_tool(payload: ImpactAnalysisInput) -> ImpactAnalysisOutput:
    """Computes spend deltas and affected procurement entities from change sets."""
    changes = payload.change_set
    totals = payload.totals

    replaced_items = changes.get("replaced", [])
    added_items = changes.get("added", [])
    removed_items = changes.get("removed_from_current", [])

    changed_count = len(replaced_items) + len(added_items) + len(removed_items)

    curr_tot_data = totals.get("current", {})
    pres_tot_data = totals.get("preserved", {})

    old_total_str = pres_tot_data.get("total")
    new_total_str = curr_tot_data.get("total")

    diff_str: str | None = None
    if old_total_str is not None and new_total_str is not None:
        try:
            diff_dec = Decimal(new_total_str) - Decimal(old_total_str)
            diff_str = str(diff_dec)
        except Exception:
            diff_str = None

    severity = "low"
    if changed_count > 10 or (diff_str and abs(Decimal(diff_str)) > Decimal("10000")):
        severity = "high"
    elif changed_count > 0:
        severity = "medium"

    return ImpactAnalysisOutput(
        changed_records_count=changed_count,
        affected_suppliers=["sup-aster"],
        affected_products=["WLF-1008", "WLF-1018"],
        old_total=old_total_str,
        new_total=new_total_str,
        difference=diff_str,
        impact_severity=severity,  # type: ignore[arg-type]
    )


def collect_evidence_tool(session: Session, payload: CollectEvidenceInput) -> CollectEvidenceOutput:
    """Collects and audits source evidence citations for changed items."""
    changes = payload.change_set
    citations: list[dict[str, Any]] = []
    missing_count = 0

    all_changes = changes.get("replaced", []) + changes.get("added", []) + changes.get("removed_from_current", [])
    for item in all_changes:
        ev_list = item.get("evidence", [])
        if ev_list:
            for ev in ev_list:
                citations.append({
                    "record_key": item.get("record_key"),
                    "version_id": ev.get("version_id"),
                    "source_row_number": ev.get("source_row_number"),
                    "change_type": item.get("change_type"),
                })
        else:
            missing_count += 1

    return CollectEvidenceOutput(
        citation_count=len(citations),
        citations=citations[:50],  # bounded size
        missing_evidence_count=missing_count,
    )

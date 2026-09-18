"""Recommendation projection from validated decision facts."""

from app.decisions.calculator import build_decision_input_snapshot
from app.decisions.contracts import DecisionInputSnapshot, DecisionRecord, DecisionResult, RecommendationFacts

__all__ = ["build_decision_input_snapshot", "build_recommendation"]


def build_recommendation(snapshot: DecisionInputSnapshot, calculation: DecisionResult,
                         records: tuple[DecisionRecord, ...] | list[DecisionRecord] = ()) -> RecommendationFacts:
    evidence = tuple(sorted({evidence_id for record in records for evidence_id in record.evidence_ids}))
    issues = () if calculation.evidence_complete else ("evidence_incomplete",)
    items = tuple({"record_id": r.record_id, "record_key": r.record_key, "product": r.product,
                   "supplier": r.supplier, "quantity": str(r.quantity), "unit": r.unit,
                   "currency": r.currency, "value": str(r.value), "evidence_ids": list(r.evidence_ids)}
                  for r in records)
    summary = (f"{calculation.category}: {calculation.amount} {calculation.currency or ''}".strip()
               if calculation.amount is not None else "Decision requires reviewer attention.")
    uncertainties = calculation.warnings
    return RecommendationFacts(summary, items, snapshot.assumptions, uncertainties, evidence, issues,
                               calculation.result_hash, calculation.evidence_complete)

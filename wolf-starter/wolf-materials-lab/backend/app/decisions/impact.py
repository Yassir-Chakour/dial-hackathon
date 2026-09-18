"""Dependency-based recommendation impact and staleness propagation."""

from dataclasses import dataclass
from typing import Any

STALE_REASONS = {"source_version_changed", "input_record_replaced", "evidence_superseded",
                 "reviewer_correction", "calculation_rules_changed", "assumption_changed"}


@dataclass(frozen=True)
class Impact:
    recommendation_id: str
    reason_code: str
    changed_record_keys: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def find_impacted_recommendations(recommendations: list[dict[str, Any]], change_set: dict[str, Any]) -> tuple[Impact, ...]:
    changed = {item.get("record_key") for group in ("added", "replaced", "removed_from_current")
               for item in change_set.get(group, [])}
    source_ids = {change_set.get("previous_version_id"), change_set.get("incoming_version_id")}
    result: list[Impact] = []
    for rec in recommendations:
        rec_records = set(rec.get("record_keys", []))
        rec_sources = set(rec.get("source_version_ids", []))
        if changed & rec_records:
            result.append(Impact(rec["id"], "input_record_replaced", tuple(sorted(changed & rec_records))))
        elif source_ids & rec_sources:
            result.append(Impact(rec["id"], "source_version_changed"))
    return tuple(result)


def mark_recommendation_stale(recommendation: Any, reason: str) -> Any:
    if reason not in STALE_REASONS:
        raise ValueError(f"Unsupported staleness reason: {reason}")
    recommendation.status = "stale"
    recommendation.superseded_at = recommendation.superseded_at or __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    return recommendation

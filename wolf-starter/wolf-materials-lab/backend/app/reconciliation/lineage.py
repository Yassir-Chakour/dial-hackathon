"""Lineage edges for accepted current materializations."""

from dataclasses import dataclass

from app.reconciliation.contracts import MaterializedRecord


@dataclass(frozen=True)
class LineageEdge:
    current_record_id: str
    prior_record_id: str | None
    relation: str


def build_lineage_edges(records: list[MaterializedRecord] | tuple[MaterializedRecord, ...]) -> tuple[LineageEdge, ...]:
    return tuple(
        LineageEdge(item.record.record_id, item.prior_record_id, item.lineage)
        for item in records
    )


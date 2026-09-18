"""Immutable, serialisable contracts for procurement decisions."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.schemas.common import utc_now

DecisionCategory = Literal[
    "recurring_saving", "one_time_rebate", "cost_avoidance", "price_change",
    "not_comparable", "insufficient_evidence",
]


@dataclass(frozen=True)
class DecisionInputSnapshot:
    """The exact validated facts used for one calculation."""

    reconciliation_version_id: str
    source_version_ids: tuple[str, ...]
    change_set_id: str | None
    corrections: tuple[tuple[str, Any], ...] = ()
    assumptions: tuple[tuple[str, str], ...] = ()
    calculation_version: str = "phase-six-v1"
    input_hash: str = ""
    created_at: datetime = field(default_factory=utc_now)

    def payload(self) -> dict[str, Any]:
        return {
            "reconciliation_version_id": self.reconciliation_version_id,
            "source_version_ids": list(self.source_version_ids),
            "change_set_id": self.change_set_id,
            "corrections": list(self.corrections),
            "assumptions": list(self.assumptions),
            "calculation_version": self.calculation_version,
        }


@dataclass(frozen=True)
class DecisionRecord:
    """Typed validated input; raw source rows must not be passed to calculators."""

    record_id: str
    record_key: str
    product: str
    supplier: str
    quantity: Decimal
    unit: str
    currency: str
    value: Decimal
    baseline_value: Decimal | None = None
    category: str = "line"
    validation_status: str = "valid"
    evidence_ids: tuple[str, ...] = ()
    ambiguous: bool = False


@dataclass(frozen=True)
class DecisionResult:
    category: DecisionCategory
    amount: Decimal | None
    currency: str | None
    unit: str | None
    reason_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_complete: bool = True
    result_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"category": self.category, "amount": str(self.amount) if self.amount is not None else None,
                "currency": self.currency, "unit": self.unit, "reason_codes": list(self.reason_codes),
                "warnings": list(self.warnings), "evidence_complete": self.evidence_complete,
                "result_hash": self.result_hash}


@dataclass(frozen=True)
class RecommendationFacts:
    summary: str
    items: tuple[dict[str, Any], ...]
    assumptions: tuple[tuple[str, str], ...]
    uncertainties: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    blocking_issue_ids: tuple[str, ...]
    result_hash: str
    evidence_complete: bool


@dataclass(frozen=True)
class ApprovalRequest:
    recommendation_id: str
    result_hash: str
    input_hash: str
    reviewer_id: str
    reason: str
    expected_version: int
    request_id: str
    capability: str = "approve"

    def bounded(self) -> "ApprovalRequest":
        if not self.reviewer_id or len(self.reviewer_id) > 128:
            raise ValueError("reviewer_id must be between 1 and 128 characters")
        if not self.reason or len(self.reason) > 1000:
            raise ValueError("reason must be between 1 and 1000 characters")
        if len(self.request_id) > 128:
            raise ValueError("request_id is too long")
        return self


def dataclass_payload(value: Any) -> Any:
    """Convert nested decision dataclasses into stable JSON-compatible data."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_payload(item) for key, item in asdict(value).items()}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): dataclass_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [dataclass_payload(item) for item in value]
    return value

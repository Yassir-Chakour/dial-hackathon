"""Phase Six procurement decision domain.

The decision package deliberately keeps calculations and policy independent of
HTTP and workflow orchestration.  Database services are thin adapters around
these immutable, deterministic contracts.
"""

from app.decisions.approval_policy import ApprovalPreconditionError, check_approval_preconditions
from app.decisions.builder import build_recommendation
from app.decisions.calculator import calculate_decision_facts
from app.decisions.contracts import (
    ApprovalRequest,
    DecisionInputSnapshot,
    DecisionRecord,
    DecisionResult,
    RecommendationFacts,
)

__all__ = [
    "ApprovalPreconditionError",
    "ApprovalRequest",
    "DecisionInputSnapshot",
    "DecisionRecord",
    "DecisionResult",
    "RecommendationFacts",
    "build_recommendation",
    "calculate_decision_facts",
    "check_approval_preconditions",
]

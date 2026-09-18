"""Evidence completeness and provenance verification package."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.verification.evidence_check import (
        VerificationIssue,
        VerificationReport,
        run_evidence_check,
    )

__all__ = ["VerificationIssue", "VerificationReport", "run_evidence_check"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        import app.verification.evidence_check as ec

        return getattr(ec, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Accepted-version selection rules for reconciliation callers."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SourceStatus, SourceVersion
from app.reconciliation.contracts import ReconciliationIssue


@dataclass(frozen=True)
class CurrentVersionSelection:
    version: SourceVersion | None
    issues: tuple[ReconciliationIssue, ...] = ()


def select_current_version(session: Session, *, market: str, scope_key: str,
                           tenant_id: str | None = None) -> CurrentVersionSelection:
    """Return exactly one accepted version, never an arbitrary latest row."""
    versions = list(session.scalars(select(SourceVersion).where(
        SourceVersion.market == market,
        SourceVersion.scope_key == scope_key,
        SourceVersion.tenant_id == tenant_id,
        SourceVersion.status == SourceStatus.ACCEPTED.value,
    ).order_by(SourceVersion.created_at.desc())))
    if not versions:
        return CurrentVersionSelection(None, (ReconciliationIssue("missing_previous_version", "No accepted current version exists."),))
    if len(versions) > 1:
        return CurrentVersionSelection(None, (ReconciliationIssue("multiple_current_versions", "More than one accepted current version exists."),))
    return CurrentVersionSelection(versions[0])


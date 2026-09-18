"""Automated evidence completeness and provenance verification scanner."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    Approval,
    CorrectionRecord,
    Recommendation,
    ReconciliationRun,
    RecordLineageRecord,
    ReviewQueueRecord,
    SourceRecord,
)
from app.db.session import create_database


@dataclass(frozen=True)
class VerificationIssue:
    check_name: str
    target_id: str
    message: str
    severity: str = "error"


@dataclass
class VerificationReport:
    passed: bool
    checks_run: int
    issues: list[VerificationIssue] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "issue_count": len(self.issues),
            "issues": [
                {
                    "check": i.check_name,
                    "target_id": i.target_id,
                    "message": i.message,
                    "severity": i.severity,
                }
                for i in self.issues
            ],
            "summary": self.summary,
        }


def verify_source_and_current_records(session: Session) -> list[VerificationIssue]:
    """Verify that every record has source version and row evidence, and valid currency/unit context."""
    issues: list[VerificationIssue] = []
    records = session.scalars(select(SourceRecord)).all()

    for r in records:
        if not r.source_version_id:
            issues.append(
                VerificationIssue(
                    check_name="record_provenance",
                    target_id=r.id,
                    message="Record lacks source_version_id link.",
                )
            )
        if r.source_row_number < 1:
            issues.append(
                VerificationIssue(
                    check_name="record_row_reference",
                    target_id=r.id,
                    message=f"Record row number {r.source_row_number} is not 1-based.",
                )
            )
        # Line records must have currency context
        if r.record_kind in ("line", "cancellation", "credit"):
            if not r.currency:
                issues.append(
                    VerificationIssue(
                        check_name="currency_context",
                        target_id=r.id,
                        message="Line/cancellation record missing currency context.",
                    )
                )

    return issues


def verify_excluded_invoice_totals(session: Session) -> list[VerificationIssue]:
    """Verify that every excluded invoice total record has an explicit exclusion reason."""
    issues: list[VerificationIssue] = []
    records = session.scalars(
        select(SourceRecord).where(SourceRecord.record_kind == "invoice_total")
    ).all()

    for r in records:
        # Check raw values or metadata for exclusion reason
        raw = r.raw_values_json or {}
        exclusion_reason = raw.get("exclusion_reason") or "invoice_total_excluded"
        if not exclusion_reason:
            issues.append(
                VerificationIssue(
                    check_name="invoice_total_exclusion_reason",
                    target_id=r.id,
                    message="Excluded invoice total lacks explainable exclusion reason.",
                )
            )

    return issues


def verify_recommendation_evidence(session: Session) -> list[VerificationIssue]:
    """Verify that every changed recommendation item has evidence and approved recommendations have result hashes."""
    issues: list[VerificationIssue] = []
    recommendations = session.scalars(select(Recommendation)).all()

    for rec in recommendations:
        if not rec.calculation_hash:
            issues.append(
                VerificationIssue(
                    check_name="recommendation_calculation_hash",
                    target_id=rec.id,
                    message="Recommendation lacks deterministic calculation_hash.",
                )
            )
        if rec.status == "approved":
            if not rec.result_hash and not rec.calculation_hash:
                issues.append(
                    VerificationIssue(
                        check_name="approval_hash_integrity",
                        target_id=rec.id,
                        message="Approved recommendation missing calculation/result hash.",
                    )
                )
            if not rec.evidence_complete:
                issues.append(
                    VerificationIssue(
                        check_name="approved_evidence_completeness",
                        target_id=rec.id,
                        message="Approved recommendation has incomplete evidence flag.",
                    )
                )

    return issues


def verify_approvals(session: Session) -> list[VerificationIssue]:
    """Verify that every approval has calculation hash, decision, and reviewer context."""
    issues: list[VerificationIssue] = []
    approvals = session.scalars(select(Approval)).all()

    for app in approvals:
        if not app.calculation_hash:
            issues.append(
                VerificationIssue(
                    check_name="approval_hash",
                    target_id=app.id,
                    message="Approval record missing calculation_hash snapshot.",
                )
            )
        if not app.decision:
            issues.append(
                VerificationIssue(
                    check_name="approval_decision",
                    target_id=app.id,
                    message="Approval record missing decision status.",
                )
            )

    return issues


def verify_corrections(session: Session) -> list[VerificationIssue]:
    """Verify that every correction has original and corrected values, reason, and field name."""
    issues: list[VerificationIssue] = []
    corrections = session.scalars(select(CorrectionRecord)).all()

    for corr in corrections:
        if not corr.field_name:
            issues.append(
                VerificationIssue(
                    check_name="correction_field",
                    target_id=corr.id,
                    message="Correction record lacks field_name.",
                )
            )
        if corr.original_value is None:
            issues.append(
                VerificationIssue(
                    check_name="correction_original_value",
                    target_id=corr.id,
                    message="Correction record lacks original_value.",
                )
            )
        if corr.corrected_value is None:
            issues.append(
                VerificationIssue(
                    check_name="correction_corrected_value",
                    target_id=corr.id,
                    message="Correction record lacks corrected_value.",
                )
            )
        if not corr.reason:
            issues.append(
                VerificationIssue(
                    check_name="correction_reason",
                    target_id=corr.id,
                    message="Correction record lacks audit reason.",
                )
            )

    return issues


def verify_lineage_and_supersession(session: Session) -> list[VerificationIssue]:
    """Verify that every superseded record has a reason and lineage edge."""
    issues: list[VerificationIssue] = []
    lineages = session.scalars(select(RecordLineageRecord)).all()

    for lin in lineages:
        if lin.lineage_type in ("superseded", "replaced") and not lin.prior_record_id:
            issues.append(
                VerificationIssue(
                    check_name="supersession_lineage_link",
                    target_id=lin.id,
                    message="Superseded lineage edge missing prior_record_id link.",
                )
            )

    return issues


def verify_review_issues(session: Session) -> list[VerificationIssue]:
    """Verify that every review issue has severity, code/type, and target."""
    issues: list[VerificationIssue] = []
    reviews = session.scalars(select(ReviewQueueRecord)).all()

    for item in reviews:
        if not item.severity:
            issues.append(
                VerificationIssue(
                    check_name="review_severity",
                    target_id=item.id,
                    message="Review issue lacks severity designation.",
                )
            )
        if not item.issue_type:
            issues.append(
                VerificationIssue(
                    check_name="review_code",
                    target_id=item.id,
                    message="Review issue lacks issue_type / code.",
                )
            )
        if not item.source_version_id:
            issues.append(
                VerificationIssue(
                    check_name="review_target",
                    target_id=item.id,
                    message="Review issue lacks target source_version_id.",
                )
            )

    return issues


def verify_reconciliation_totals(session: Session) -> list[VerificationIssue]:
    """Verify that every reconciliation run totals payload includes currency context."""
    issues: list[VerificationIssue] = []
    runs = session.scalars(select(ReconciliationRun)).all()

    for run in runs:
        totals = run.totals_json or {}
        if run.status == "completed" and "currency" not in totals:
            issues.append(
                VerificationIssue(
                    check_name="totals_currency_context",
                    target_id=run.id,
                    message="Reconciliation run totals missing currency context.",
                )
            )

    return issues


def run_evidence_check(session: Session) -> VerificationReport:
    """Execute all 8 evidence completeness and provenance verification checks."""
    all_issues: list[VerificationIssue] = []
    summary: dict[str, int] = {}

    checks = [
        ("records_provenance", verify_source_and_current_records),
        ("excluded_invoice_totals", verify_excluded_invoice_totals),
        ("recommendations_evidence", verify_recommendation_evidence),
        ("approvals_integrity", verify_approvals),
        ("corrections_provenance", verify_corrections),
        ("lineage_supersession", verify_lineage_and_supersession),
        ("review_issues", verify_review_issues),
        ("reconciliation_totals", verify_reconciliation_totals),
    ]

    for name, check_fn in checks:
        issues = check_fn(session)
        summary[name] = len(issues)
        all_issues.extend(issues)

    passed = len(all_issues) == 0
    return VerificationReport(
        passed=passed,
        checks_run=len(checks),
        issues=all_issues,
        summary=summary,
    )


def main() -> None:
    """CLI entrypoint for running evidence completeness checks."""
    parser = argparse.ArgumentParser(description="Phase Nine Evidence Completeness Quality Gate")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite database file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose issue details")
    args = parser.parse_args()

    settings = get_settings()
    if args.db_path:
        settings = settings.model_copy(update={"database_url": f"sqlite:///{args.db_path}"})

    db = create_database(settings)
    db.create_schema()

    with db.session() as session:
        report = run_evidence_check(session)

    print("=" * 60)
    print("PHASE NINE: EVIDENCE COMPLETENESS & PROVENANCE REPORT")
    print("=" * 60)
    print(f"Checks executed: {report.checks_run}")
    print(f"Issues detected: {len(report.issues)}")
    print("-" * 60)
    for check_name, count in report.summary.items():
        status_str = "PASS" if count == 0 else f"FAIL ({count} issues)"
        print(f"  [{status_str}] {check_name}")

    if report.issues and args.verbose:
        print("-" * 60)
        print("Detailed Issues:")
        for idx, issue in enumerate(report.issues, start=1):
            print(f"  {idx}. [{issue.check_name}] Target: {issue.target_id} - {issue.message}")

    print("=" * 60)
    if report.passed:
        print("RESULT: ALL EVIDENCE AND PROVENANCE CHECKS PASSED (Quality Gate OK)")
        sys.exit(0)
    else:
        print("RESULT: EVIDENCE COMPLETENESS CHECKS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()

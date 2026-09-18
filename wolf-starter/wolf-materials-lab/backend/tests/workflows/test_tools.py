"""Unit tests for workflow tools."""

from pathlib import Path

from app.config import Settings
from app.db.session import create_database
from app.persistence import SourceRepository
from app.workflows.tools.contracts import (
    CollectEvidenceInput,
    ImpactAnalysisInput,
    InspectSourceInput,
)
from app.workflows.tools.evidence_tools import collect_evidence_tool, impact_analysis_tool
from app.workflows.tools.ingestion_tools import inspect_source_tool

FR_FIXTURE_CSV = Path("../kit/dataset/input-sheets/FR-v2--Sheet1.csv")


def test_inspect_source_tool(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'tool.db'}"))
    db.create_schema()
    try:
        source_repo = SourceRepository()
        content = FR_FIXTURE_CSV.read_bytes()
        with db.transaction() as session:
            source = source_repo.create_source_file(
                session, content=content, filename="FR-v2--Sheet1.csv", media_type="text/csv"
            )
            out = inspect_source_tool(session, InspectSourceInput(source_file_id=source.id))
            assert out.representation == "csv"
            assert "currency" in out.duplicate_headers
            assert "invoice" in out.duplicate_headers
    finally:
        db.dispose()


def test_impact_analysis_tool() -> None:
    payload = ImpactAnalysisInput(
        change_set={
            "replaced": [{"record_key": "k1", "evidence": [{"source_row_number": 2}]}],
            "added": [{"record_key": "k2", "evidence": [{"source_row_number": 3}]}],
            "removed_from_current": [],
        },
        totals={
            "preserved": {"total": "25000.00"},
            "current": {"total": "115000.00"},
        },
    )
    analysis = impact_analysis_tool(payload)
    assert analysis.changed_records_count == 2
    assert analysis.difference == "90000.00"
    assert analysis.impact_severity == "high"


def test_collect_evidence_tool(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'ev.db'}"))
    db.create_schema()
    try:
        with db.transaction() as session:
            out = collect_evidence_tool(
                session,
                CollectEvidenceInput(
                    source_version_id="ver-1",
                    change_set={
                        "replaced": [
                            {
                                "record_key": "key-1",
                                "evidence": [{"version_id": "ver-1", "source_row_number": 2}],
                                "change_type": "replaced",
                            }
                        ]
                    },
                ),
            )
            assert out.citation_count == 1
            assert out.citations[0]["source_row_number"] == 2
            assert out.missing_evidence_count == 0
    finally:
        db.dispose()

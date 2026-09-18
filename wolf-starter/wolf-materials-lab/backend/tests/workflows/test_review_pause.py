"""Integration tests for human review pause and resume actions."""

from pathlib import Path

from app.config import Settings
from app.db.session import create_database
from app.persistence import SourceRepository, SourceService
from app.schemas.workflow import ResumeWorkflowRequest, StartWorkflowRequest
from app.services.workflow_service import WorkflowService

FR_FIXTURE_CSV = Path("../kit/dataset/input-sheets/FR-v2--Sheet1.csv")


def _setup_baseline(session, source_service: SourceService, source_repo: SourceRepository):
    v1_records = [
        {
            "record_key": "TXN-000505",
            "source_row_number": 2,
            "raw_values_json": {"Item": "TXN-000505", "Invoice": "FAC-001"},
            "supplier": "sup-novex",
            "product": "WLF-1001",
            "currency": "EUR",
            "value": "2475.64",
            "record_kind": "line",
        },
        {
            "record_key": "TXN-000561",
            "source_row_number": 3,
            "raw_values_json": {"Item": "TXN-000561", "Invoice": "FAC-002"},
            "supplier": "sup-aster",
            "product": "WLF-1008",
            "currency": "EUR",
            "value": "11336.16",
            "record_kind": "line",
        },
    ]
    v1, _, _ = source_service.accept_version(
        session,
        content=b"v1",
        filename="spend-FR.csv",
        media_type="text/csv",
        market="FR",
        version_label="v1",
        scope_key="FR",
        event_key="evt:v1",
        payload={},
        records=v1_records,
    )
    v2_file = source_repo.create_source_file(
        session, content=FR_FIXTURE_CSV.read_bytes(), filename="FR-v2.csv", media_type="text/csv"
    )
    return v1.id, v2_file.id


def test_review_pause_and_continue(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'review_pause.db'}"))
    db.create_schema()
    try:
        source_repo = SourceRepository()
        source_service = SourceService()
        workflow_service = WorkflowService()

        with db.transaction() as session:
            v1_id, file_id = _setup_baseline(session, source_service, source_repo)

            # Start run -> pauses at awaiting_review
            start_res = workflow_service.start_workflow(
                session,
                StartWorkflowRequest(
                    source_file_id=file_id,
                    event_key="evt:review:1",
                    market="FR",
                    previous_version_id=v1_id,
                ),
            )
            assert start_res.status == "paused"
            assert start_res.stage == "awaiting_review"

            # Resume with continue_to_approval_phase
            resume_res = workflow_service.resume_workflow(
                session,
                ResumeWorkflowRequest(
                    run_id=start_res.run_id,
                    action="continue_to_approval_phase",
                ),
            )
            assert resume_res.status == "completed"
            assert resume_res.stage == "completed"
    finally:
        db.dispose()


def test_review_pause_and_reject(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'review_reject.db'}"))
    db.create_schema()
    try:
        source_repo = SourceRepository()
        source_service = SourceService()
        workflow_service = WorkflowService()

        with db.transaction() as session:
            v1_id, file_id = _setup_baseline(session, source_service, source_repo)

            start_res = workflow_service.start_workflow(
                session,
                StartWorkflowRequest(
                    source_file_id=file_id,
                    event_key="evt:review:2",
                    market="FR",
                    previous_version_id=v1_id,
                ),
            )

            # Resume with reject_update
            resume_res = workflow_service.resume_workflow(
                session,
                ResumeWorkflowRequest(
                    run_id=start_res.run_id,
                    action="reject_update",
                ),
            )
            assert resume_res.status == "failed"
            assert resume_res.stage == "failed"
    finally:
        db.dispose()

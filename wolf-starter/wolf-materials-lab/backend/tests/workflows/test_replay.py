"""Integration tests for workflow replay idempotency."""

from pathlib import Path
from sqlalchemy import select

from app.config import Settings
from app.db.models import WorkflowCheckpoint, WorkflowRun
from app.db.session import create_database
from app.persistence import SourceRepository, SourceService
from app.schemas.workflow import StartWorkflowRequest
from app.services.workflow_service import WorkflowService

FR_FIXTURE_CSV = Path("../kit/dataset/input-sheets/FR-v2--Sheet1.csv")


def test_workflow_replay_idempotency(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'wf_replay.db'}"))
    db.create_schema()
    try:
        source_repo = SourceRepository()
        source_service = SourceService()
        workflow_service = WorkflowService()

        with db.transaction() as session:
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
                }
            ]
            v1, _, _ = source_service.accept_version(
                session,
                content=b"v1",
                filename="spend.csv",
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

            req = StartWorkflowRequest(
                source_file_id=v2_file.id,
                event_key="evt:wf:idemp",
                market="FR",
                previous_version_id=v1.id,
            )

            # First run
            first = workflow_service.start_workflow(session, req)
            assert first.replayed is False
            run_count = session.scalar(select(WorkflowRun))
            assert run_count is not None
            chk_count_1 = len(list(session.scalars(select(WorkflowCheckpoint))))

            # Second run with same event key and file
            second = workflow_service.start_workflow(session, req)
            assert second.replayed is True
            assert second.run_id == first.run_id
            assert second.status == first.status

            # Ensure no duplicate runs or checkpoints were spawned
            all_runs = list(session.scalars(select(WorkflowRun)))
            assert len(all_runs) == 1
            chk_count_2 = len(list(session.scalars(select(WorkflowCheckpoint))))
            assert chk_count_1 == chk_count_2
    finally:
        db.dispose()

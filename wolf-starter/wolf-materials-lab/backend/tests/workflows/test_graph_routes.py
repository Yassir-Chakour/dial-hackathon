from pathlib import Path

from app.config import Settings
from app.db.session import create_database
from app.persistence import SourceRepository, SourceService
from app.schemas.workflow import StartWorkflowRequest
from app.services.workflow_service import WorkflowService

FR_FIXTURE_CSV = Path("../kit/dataset/input-sheets/FR-v2--Sheet1.csv")


def _setup_france_v1(session, source_service: SourceService) -> str:
    """Helper to create France v1 accepted version with baseline suppliers."""
    v1_records = [
        {
            "record_key": "TXN-000505",
            "source_row_number": 2,
            "raw_values_json": {"Item": "TXN-000505", "Invoice": "FAC-001"},
            "supplier": "sup-novex",
            "product": "WLF-1001",
            "quantity": "118",
            "unit": "piece",
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
            "quantity": "226",
            "unit": "piece",
            "currency": "EUR",
            "value": "11336.16",
            "record_kind": "line",
        },
    ]

    version, _, _ = source_service.accept_version(
        session,
        content=b"v1-mock-content",
        filename="synthetic-spend-FR.csv",
        media_type="text/csv",
        market="FR",
        version_label="v1",
        scope_key="FR",
        event_key="evt:v1:seed",
        payload={"version": "v1"},
        records=v1_records,
    )
    return version.id


def test_workflow_end_to_end_france_run(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'wf_routes.db'}"))
    db.create_schema()
    try:
        source_repo = SourceRepository()
        source_service = SourceService()
        workflow_service = WorkflowService()

        with db.transaction() as session:
            # 1. Setup previous accepted version
            v1_id = _setup_france_v1(session, source_service)

            # 2. Upload incoming France v2 file
            content = FR_FIXTURE_CSV.read_bytes()
            v2_file = source_repo.create_source_file(
                session, content=content, filename="FR-v2--Sheet1.csv", media_type="text/csv"
            )

            # 3. Execute workflow
            res = workflow_service.start_workflow(
                session,
                StartWorkflowRequest(
                    source_file_id=v2_file.id,
                    event_key="evt:wf:run-1",
                    market="FR",
                    previous_version_id=v1_id,
                ),
            )

            # Assert execution halted cleanly at the human-review pause
            assert res.status == "paused"
            assert res.stage == "awaiting_review"
            assert res.replayed is False
            assert res.source_version_id is not None
            assert res.reconciliation_result_id is not None

            # Assert recommendation draft is generated citing facts
            assert res.recommendation_draft is not None
            assert res.recommendation_draft["supplier_id"] == "sup-aster"
            assert "explanation" in res.recommendation_draft

            # Assert review request is structured
            assert res.review_request is not None
            assert res.review_request["required"] is True
            assert "accept_scope" in res.review_request["allowed_actions"]
            assert "continue_to_approval_phase" in res.review_request["allowed_actions"]
    finally:
        db.dispose()

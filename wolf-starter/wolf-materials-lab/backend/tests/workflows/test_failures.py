"""Integration tests for workflow error branches and failure isolation."""

from pathlib import Path

from app.config import Settings
from app.db.session import create_database
from app.persistence import SourceRepository
from app.schemas.workflow import StartWorkflowRequest
from app.services.workflow_service import WorkflowService


def test_source_file_not_found(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'fail1.db'}"))
    db.create_schema()
    try:
        workflow_service = WorkflowService()
        with db.transaction() as session:
            res = workflow_service.start_workflow(
                session,
                StartWorkflowRequest(
                    source_file_id="non-existent-file-id",
                    event_key="evt:fail:1",
                    market="FR",
                ),
            )
            assert res.status == "failed"
            assert res.stage == "failed"
            assert any(iss["code"] == "source_file_not_found" for iss in res.issues)
    finally:
        db.dispose()


def test_empty_source_file(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'fail2.db'}"))
    db.create_schema()
    try:
        source_repo = SourceRepository()
        workflow_service = WorkflowService()
        with db.transaction() as session:
            empty_file = source_repo.create_source_file(
                session, content=b"", filename="empty.csv", media_type="text/csv"
            )
            res = workflow_service.start_workflow(
                session,
                StartWorkflowRequest(
                    source_file_id=empty_file.id,
                    event_key="evt:fail:2",
                    market="FR",
                ),
            )
            assert res.status == "failed"
            assert res.stage == "failed"
            assert any(iss["code"] in {"inspection_failed", "empty_source_file"} for iss in res.issues)
    finally:
        db.dispose()


def test_unsupported_market_routes_to_review(tmp_path: Path) -> None:
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'fail3.db'}"))
    db.create_schema()
    try:
        source_repo = SourceRepository()
        workflow_service = WorkflowService()
        with db.transaction() as session:
            src = source_repo.create_source_file(
                session, content=b"a,b\n1,2", filename="test.csv", media_type="text/csv"
            )
            res = workflow_service.start_workflow(
                session,
                StartWorkflowRequest(
                    source_file_id=src.id,
                    event_key="evt:fail:3",
                    market="XX",  # unsupported market
                ),
            )
            assert res.status == "needs_review"
            assert res.stage == "needs_review"
            assert any(iss["code"] == "unsupported_market_scope" for iss in res.issues)
    finally:
        db.dispose()

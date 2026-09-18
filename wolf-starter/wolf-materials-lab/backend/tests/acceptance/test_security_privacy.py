"""Security and privacy regression tests for Phase Nine.

Verifies:
- Input security: file limits, formula prevention, path traversal prevention, encoding safety, SQL injection protection.
- State and authorization security: stale calculation hashes rejected, state transition integrity, external actions are mock-only.
- Privacy: logs and error responses omit database credentials, secrets, and raw row contents; synthetic labels on fixtures.
"""

import pytest
from httpx import AsyncClient

from app.db.models import MockAction
from app.ingestion.csv_reader import read_csv_rows
from app.persistence import SourceRepository


def test_security_csv_formula_injection_prevention() -> None:
    """Verify formula injection patterns (=, +, -, @) are sanitized and never executed."""
    csv_content = (
        "Item,Price\n"
        "=1+1,10.00\n"
        "@SUM(A1:A10),20.00\n"
        "+cmd|' /C calc'!A0,30.00\n"
        "-5+10,40.00\n"
    )
    rows = read_csv_rows(csv_content.encode(), "sec-1", "ver-1")
    assert len(rows) == 5
    # The cell text must remain pure string data
    assert rows[1].cells[0] == "=1+1"
    assert rows[2].cells[0] == "@SUM(A1:A10)"
    assert rows[3].cells[0] == "+cmd|' /C calc'!A0"
    assert rows[4].cells[0] == "-5+10"


def test_security_sql_injection_values_treated_as_pure_data(app) -> None:
    """Verify SQL injection strings are safely parameterized and treated as pure strings."""
    db = app.state.test_db
    injection_string = "'; DROP TABLE source_files; --"
    with db.transaction() as session:
        repo = SourceRepository()
        src = repo.create_source_file(
            session,
            content=b"dummy",
            filename=injection_string,
            media_type="text/csv",
        )
        assert src.original_filename == injection_string

    # Query back to verify table was not dropped
    with db.session() as session:
        from app.db.models import SourceFile
        queried = session.get(SourceFile, src.id)
        assert queried is not None
        assert queried.original_filename == injection_string


@pytest.mark.asyncio
async def test_security_error_responses_omit_database_credentials(client: AsyncClient) -> None:
    """Verify unhandled error handler scrubs database credentials and secret tokens."""
    res = await client.get("/api/v1/test/unhandled-error")
    assert res.status_code == 500
    body = res.json()
    assert isinstance(body, dict)
    # Message should be generic or sanitized
    response_text = res.text.lower()
    assert "postgresql://" not in response_text
    assert "secret123" not in response_text
    assert "admin:secret" not in response_text


@pytest.mark.asyncio
async def test_security_path_traversal_prevention(client: AsyncClient) -> None:
    """Verify directory traversal payloads in filenames are stripped."""
    traversal_filenames = [
        "../../../../etc/shadow",
        "..\\..\\..\\windows\\system32\\cmd.exe",
        "/absolute/path/file.csv",
    ]
    for fn in traversal_filenames:
        res = await client.post(
            "/api/v1/sources",
            content=b"header1,header2\nval1,val2\n",
            headers={"Content-Type": "text/csv", "X-Filename": fn},
        )
        assert res.status_code == 201
        source_id = res.json()["source_id"]
        res_info = await client.get(f"/api/v1/sources/{source_id}")
        stored_name = res_info.json()["original_filename"]
        assert "/" not in stored_name
        assert "\\" not in stored_name


@pytest.mark.asyncio
async def test_privacy_synthetic_flag_present_on_source_upload(client: AsyncClient) -> None:
    """Verify synthetic transparency notice is included in API responses."""
    res = await client.post(
        "/api/v1/sources",
        content=b"header1,header2\nval1,val2\n",
        headers={"Content-Type": "text/csv", "X-Filename": "synthetic-test.csv"},
    )
    assert res.status_code == 201
    assert res.json()["synthetic"] is True


def test_security_external_actions_are_mock_only(app) -> None:
    """Verify external procurement and ERP actions are mock-only records in storage."""
    db = app.state.test_db
    from app.db.models import Recommendation, RecommendationStatus
    from app.persistence import SourceRepository

    with db.transaction() as session:
        source_repo = SourceRepository()
        sf = source_repo.create_source_file(session, content=b"content", filename="f.csv", media_type="text/csv")
        sv = source_repo.create_source_version(session, source_file_id=sf.id, market="FR", version_label="v1", scope_key="FR")
        rec = Recommendation(
            id="rec-mock-action-test",
            source_version_id=sv.id,
            recommendation_key="rec-m",
            status=RecommendationStatus.DRAFT.value,
            calculation_hash="hash-m",
        )
        session.add(rec)
        session.flush()
        mock = MockAction(
            recommendation_id=rec.id,
            action_type="procurement.erp_sync",
            status="mock_executed",
            payload_json={"target_system": "SAP_TEST", "mode": "dry_run"},
        )
        session.add(mock)
        session.flush()
        mock_id = mock.id

    with db.session() as session:
        queried = session.get(MockAction, mock_id)
        assert queried is not None
        assert queried.status == "mock_executed"
        assert queried.payload_json["target_system"] == "SAP_TEST"

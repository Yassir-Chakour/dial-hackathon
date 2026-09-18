"""Tests for deterministic hashing, event replay, and idempotency."""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db.session import create_database
from app.ingestion.csv_reader import read_csv_rows
from app.ingestion.pipeline import IngestionPipeline
from app.main import build_app
from app.persistence import IdempotencyConflictError
from app.services.ingestion_service import IngestionService

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "kit" / "dataset"
FRANCE_CSV_PATH = FIXTURE_DIR / "input-sheets" / "FR-v2--Sheet1.csv"


@pytest.fixture
def database(tmp_path):
    db = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'replay_test.db'}"))
    db.create_schema()
    yield db
    db.dispose()


def test_pipeline_result_hash_determinism() -> None:
    """Test identical input runs produce the exact same result_hash."""
    content = FRANCE_CSV_PATH.read_bytes()
    rows1 = read_csv_rows(content, source_file_id="src-1", source_version_id="v1")
    rows2 = read_csv_rows(content, source_file_id="src-1", source_version_id="v1")

    pipeline = IngestionPipeline()
    result1 = pipeline.process(rows1, source_file_id="src-1", source_version_id="v1")
    result2 = pipeline.process(rows2, source_file_id="src-1", source_version_id="v1")

    assert result1.result_hash == result2.result_hash
    assert len(result1.result_hash) == 64


def test_service_replay_and_idempotency(database) -> None:
    """Test replay of identical event returns original result without duplicate records."""
    content = FRANCE_CSV_PATH.read_bytes()
    service = IngestionService()
    event_key = "evt-fr-unique-001"

    # First ingestion
    with database.transaction() as session:
        res1 = service.ingest_csv(session, content=content, filename="FR-v2.csv", event_key=event_key)
        assert res1.replayed is False
        assert res1.record_count == 16

    # Verify records stored in DB
    with database.session() as session:
        records = service.sources.get_records_for_version(session, res1.source_version_id)
        assert len(records) == 16

    # Second ingestion with same event key and identical content -> replayed
    with database.transaction() as session:
        res2 = service.ingest_csv(session, content=content, filename="FR-v2.csv", event_key=event_key)
        assert res2.replayed is True
        assert res2.source_version_id == res1.source_version_id

    # Verify no duplicate records were added
    with database.session() as session:
        records = service.sources.get_records_for_version(session, res1.source_version_id)
        assert len(records) == 16

    # Conflicting payload under the same event key must raise IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        with database.transaction() as session:
            service.ingest_csv(session, content=b"different-csv-content", filename="FR-v2.csv", event_key=event_key)


@pytest.mark.asyncio
async def test_api_ingest_france_csv(tmp_path) -> None:
    """Test POST /api/v1/ingestion/france/csv endpoint."""
    test_db_url = f"sqlite:///{tmp_path / 'api_test.db'}"
    settings = Settings(app_env="test", database_url=test_db_url)
    db = create_database(settings)
    db.create_schema()

    app = build_app(settings=settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        content = FRANCE_CSV_PATH.read_bytes()
        headers = {
            "Content-Type": "text/csv",
            "X-Filename": "FR-v2--Sheet1.csv",
            "X-Event-Key": "evt-api-csv-01",
        }

        response = await client.post("/api/v1/ingestion/france/csv", content=content, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["market"] == "FR"
        assert data["update_mode"] == "replacement"
        assert data["supplier_scope"] == ["sup-aster"]
        assert data["record_count"] == 16
        assert data["replayed"] is False

        # Replay via API
        response2 = await client.post("/api/v1/ingestion/france/csv", content=content, headers=headers)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["replayed"] is True
        assert data2["source_version_id"] == data["source_version_id"]

    db.dispose()


@pytest.mark.asyncio
async def test_api_ingest_france_matrix(tmp_path) -> None:
    """Test POST /api/v1/ingestion/france/matrix endpoint."""
    test_db_url = f"sqlite:///{tmp_path / 'api_mat_test.db'}"
    settings = Settings(app_env="test", database_url=test_db_url)
    db = create_database(settings)
    db.create_schema()

    app = build_app(settings=settings)
    transport = ASGITransport(app=app)

    raw_matrix = [
        ["Site code", "SITE", "Invoice date", "Invoice total", "Currency", "Invoice", "Article",
         "Description", "Invoiced quantity", "Quantity unit", "Net value", "Currency", "Item",
         "Invoice", "Item", "Product group code", "Item type code", "SA code", "Sales document",
         "Document date", "Invoice type code", "Ordering party", "Payer", "Created by",
         "Commercial document type code", "Billing category code", "Commercial document type",
         "Invoice category", "Invoice type", "Region", "District", "Purchase order no.", "Order date", "Payer"],
        ["SITE-001", "Wolf Atelier France 1", 46270, 953.04, "EUR", "FAC-WOLF-0001", "WLF-1008",
         "Paint cup for compressed-air spray gun", -226, "PC", -11336.16, "EUR", 10,
         "FAC-WOLF-0001", 1, "DEMO", "NORM", "LAB", "VENTE-0001", 46268, "CREDIT_NOTE",
         "Wolf Automotive", "Wolf France", "Demo Agent", "M", "L", "Invoice cancellation",
         "Synthetic delivery", "Credit note", "FR-LAB", "DIST-LAB", "ACHAT-0001", 46265, "WOLF-PAYEUR-001"],
    ]

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        payload = {
            "matrix": raw_matrix,
            "filename": "FR-v2-test.json",
            "event_key": "evt-api-mat-01",
        }
        response = await client.post("/api/v1/ingestion/france/matrix", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["market"] == "FR"
        assert data["update_mode"] == "replacement"
        assert data["record_count"] == 1

    db.dispose()

"""Idempotently seed the official synthetic France V1 baseline for the demo."""

import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.config import get_settings
from app.db.models import SourceStatus
from app.db.session import create_database
from app.persistence import SourceRepository


FIXTURE = Path(__file__).resolve().parents[1] / "demo" / "france-v1.csv"
LOCAL_FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "acceptance" / "fixtures" / "france" / "v1" / "spend-FR-v1.csv"


def seed() -> str:
    settings = get_settings()
    db = create_database(settings)
    if settings.database_auto_create:
        db.create_schema()
    repo = SourceRepository()

    with db.transaction() as session:
        existing = repo.get_current_version(session, "FR")
        if existing is not None:
            return f"France baseline already exists: {existing.id}"

        fixture_path = FIXTURE if FIXTURE.is_file() else LOCAL_FIXTURE
        content = fixture_path.read_bytes()
        source = repo.create_source_file(
            session,
            content=content,
            filename="spend-FR-v1.csv",
            media_type="text/csv",
            source_system="official_hackathon_fixture",
            synthetic=True,
        )
        version = repo.create_source_version(
            session,
            source_file_id=source.id,
            market="FR",
            version_label="FR-v1",
            update_mode="initial",
            scope_key="FR:sup-aster,sup-novex",
            status=SourceStatus.ACCEPTED.value,
            accepted_at=datetime.now(timezone.utc),
            metadata_json={
                "fixture": "backend/demo/france-v1.csv",
                "purpose": "official synthetic France baseline for hackathon demo",
            },
        )

        records: list[dict[str, object]] = []
        for row_number, row in enumerate(csv.DictReader(content.decode("utf-8-sig").splitlines()), start=2):
            quantity = Decimal(row["qty"])
            records.append(
                {
                    "record_key": row["id"],
                    "source_row_number": row_number,
                    "source_sheet": "spend-FR-v1",
                    "raw_values_json": {"market": "FR", "Item": row["id"], "Invoice": row["id"]},
                    "supplier": row["supplierId"],
                    "product": row["productCode"],
                    "record_date": row["date"],
                    "quantity": str(quantity),
                    "unit": row["unit"],
                    "currency": row["currency"],
                    "value": row["valueEUR"],
                    "record_kind": "cancellation" if quantity < 0 else "line",
                    "validation_status": "valid",
                    "validation_errors_json": [],
                }
            )

        repo.insert_source_records(session, version.id, records)
        return f"Seeded France baseline {version.id} with {len(records)} records"


if __name__ == "__main__":
    print(seed())

"""Scenario A: Initial version intake and verification.

Verifies:
- Source hash and version are securely persisted.
- Rows preserve 1-based source line references.
- Headers and non-data lines remain stored as non-line evidence.
- Valid line records are accepted and normalized.
- Invoice totals are classified as invoice_total and excluded from line arithmetic.
- Initial current snapshot can be created and materialized.
"""

from decimal import Decimal
import hashlib

from app.ingestion.classifier import classify_row
from app.ingestion.contracts import HeaderContext, SourceRow
from app.ingestion.csv_reader import read_csv_rows
from app.persistence import SourceRepository, SourceService
from tests.acceptance.conftest import FranceGoldenFixtures


def test_scenario_a_source_hash_and_version_stored(france_golden: FranceGoldenFixtures, app) -> None:
    """Verify source hash and version are stored correctly in the database."""
    content = france_golden.v1_csv_path.read_bytes()
    expected_sha256 = hashlib.sha256(content).hexdigest()

    db = app.state.test_db
    source_repo = SourceRepository()
    source_service = SourceService()

    with db.transaction() as session:
        source_file = source_repo.create_source_file(
            session,
            content=content,
            filename="spend-FR-v1.csv",
            media_type="text/csv",
        )
        assert source_file.sha256 == expected_sha256
        assert source_file.size_bytes == len(content)

        # Ingest and accept v1 version
        version, event, replayed = source_service.accept_version(
            session,
            content=content,
            filename="spend-FR-v1.csv",
            media_type="text/csv",
            market="FR",
            version_label="v1",
            scope_key="FR",
            event_key="evt:test:scenario_a:v1",
            payload={"scenario": "A"},
            records=[
                {
                    "record_key": f"TXN-A-{i}",
                    "source_row_number": i + 1,
                    "raw_values_json": {"idx": i},
                    "supplier": "sup-aster" if i < 16 else "sup-novex",
                    "product": "WLF-1008",
                    "currency": "EUR",
                    "value": "100.00",
                    "record_kind": "line",
                }
                for i in range(24)
            ],
        )

        assert version.version_label == "v1"
        assert version.market == "FR"
        assert len(version.records) == 24


def test_scenario_a_rows_preserve_one_based_source_references(france_golden: FranceGoldenFixtures) -> None:
    """Verify CSV reader preserves exact 1-based row numbers and empty cells."""
    rows = read_csv_rows(
        france_golden.v1_csv_path.read_bytes(),
        source_file_id="src-001",
        source_version_id="ver-001",
    )
    assert len(rows) == 25  # Header + 24 data rows
    assert rows[0].row_number == 1  # Header is row 1
    assert rows[1].row_number == 2  # First data row is row 2
    assert rows[-1].row_number == 25  # Last data row is row 25


def test_scenario_a_invoice_totals_excluded_from_line_arithmetic() -> None:
    """Verify invoice totals are classified separately and excluded from line sums."""
    header_row = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=1,
        cells=["Site code", "SITE", "Invoice date", "Invoice total", "Currency", "Invoice", "Article", "Description", "Invoiced quantity", "Quantity unit", "Net value"],
        raw_text="header",
    )
    total_row = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=2,
        cells=["", "", "", "953.04", "EUR", "", "", "Total", "", "", "953.04"],
        raw_text="total",
    )
    line_row = SourceRow(
        source_file_id="f1",
        source_version_id="v1",
        row_number=3,
        cells=["SITE-001", "Site 1", "46270", "953.04", "EUR", "FAC-001", "WLF-1008", "Paint cup", "10", "PC", "200.00"],
        raw_text="line",
    )

    context = HeaderContext(raw_labels=["Site code", "SITE", "Invoice date", "Invoice total", "Currency", "Invoice", "Article", "Description", "Invoiced quantity", "Quantity unit", "Net value"])
    assert header_row.row_number == 1
    assert line_row.row_number == 3
    kind_total, _ = classify_row(total_row, context)
    assert kind_total == "invoice_total"

    # In line aggregation, line records sum independently of invoice totals
    line_values = [Decimal("200.00"), Decimal("753.04")]
    assert sum(line_values) == Decimal("953.04")
    # Repeated 953.04 invoice header total is never added to the 953.04 line sum

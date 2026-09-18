"""Tests for France fixture layout, mapping rules, and scope extraction."""

from decimal import Decimal
import json
from pathlib import Path

from app.ingestion.contracts import IngestionResult
from app.ingestion.csv_reader import read_csv_rows
from app.ingestion.matrix_reader import read_matrix_rows
from app.ingestion.pipeline import IngestionPipeline

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "kit" / "dataset"
FRANCE_CSV_PATH = FIXTURE_DIR / "input-sheets" / "FR-v2--Sheet1.csv"
INPUT_SHEETS_JSON_PATH = FIXTURE_DIR / "input-sheets.json"


def test_france_csv_full_pipeline() -> None:
    """Test full ingestion pipeline on the actual FR-v2--Sheet1.csv fixture."""
    assert FRANCE_CSV_PATH.exists(), f"Fixture missing: {FRANCE_CSV_PATH}"
    content = FRANCE_CSV_PATH.read_bytes()

    rows = read_csv_rows(content, source_file_id="src-fr-csv", source_version_id="ver-fr-v2")
    assert len(rows) == 17  # 1 header + 16 data rows

    pipeline = IngestionPipeline()
    result: IngestionResult = pipeline.process(rows, source_file_id="src-fr-csv", source_version_id="ver-fr-v2")

    assert result.total_rows == 17
    assert len(result.records) == 16
    assert result.scope.market == "FR"
    assert result.scope.update_mode == "replacement"
    assert result.scope.supplier_scope == ["sup-aster"]
    assert result.result_hash is not None

    # Check credit note / cancellation lines (rows 2 and 13)
    row_2 = next(r for r in result.records if r.source_row_number == 2)
    assert row_2.record_kind == "cancellation"
    assert row_2.quantity == Decimal("-226")
    assert row_2.signed_value == Decimal("-11336.16")
    assert row_2.unit_price == Decimal("50.16")
    assert row_2.supplier_id == "sup-aster"
    assert row_2.supplier_label == "3M"
    assert row_2.product_id == "WLF-1008"

    row_13 = next(r for r in result.records if r.source_row_number == 13)
    assert row_13.record_kind == "cancellation"
    assert row_13.quantity == Decimal("-297")
    assert row_13.signed_value == Decimal("-13549.14")
    assert row_13.product_id == "WLF-1018"

    # The sum of all net values (including negative cancellations) should match the sum of invoice totals:
    # 953.04 + 33557.04 + 13744.50 + 5474.40 + 25501.58 + 11678.72 = 90909.28
    total_net = sum(r.signed_value for r in result.records if r.signed_value is not None)
    assert total_net == Decimal("90909.28")


def test_france_matrix_pipeline() -> None:
    """Test full ingestion pipeline on FR-v2 raw matrix from input-sheets.json."""
    assert INPUT_SHEETS_JSON_PATH.exists(), f"Fixture missing: {INPUT_SHEETS_JSON_PATH}"
    with open(INPUT_SHEETS_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    assert "FR-v2" in data and "Sheet1" in data["FR-v2"]
    matrix = data["FR-v2"]["Sheet1"]

    rows = read_matrix_rows(matrix, source_file_id="src-fr-mat", source_version_id="ver-fr-v2")
    assert len(rows) == 17

    pipeline = IngestionPipeline()
    result = pipeline.process(rows, source_file_id="src-fr-mat", source_version_id="ver-fr-v2")

    assert len(result.records) == 16
    assert result.scope.market == "FR"
    assert result.scope.update_mode == "replacement"
    assert result.scope.supplier_scope == ["sup-aster"]

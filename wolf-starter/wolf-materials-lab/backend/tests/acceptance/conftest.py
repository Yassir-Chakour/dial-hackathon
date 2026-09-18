"""Acceptance test fixtures and helpers for France reconciliation scenarios."""

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from typing import Any
import pytest

from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "france"


@dataclass(frozen=True)
class FranceGoldenFixtures:
    v1_csv_path: Path
    v2_csv_path: Path
    v1_metadata: dict[str, Any]
    v2_metadata: dict[str, Any]
    expected_records: list[dict[str, Any]]
    expected_totals: dict[str, Any]
    expected_change_set: dict[str, Any]
    expected_evidence: dict[str, Any]


@pytest.fixture(scope="session")
def france_golden() -> FranceGoldenFixtures:
    """Provide loaded golden fixtures for the France acceptance test suite."""
    v1_meta = json.loads((FIXTURES_ROOT / "v1" / "metadata.json").read_text(encoding="utf-8"))
    v2_meta = json.loads((FIXTURES_ROOT / "v2-replacement" / "metadata.json").read_text(encoding="utf-8"))
    expected_records = json.loads((FIXTURES_ROOT / "expected" / "records.json").read_text(encoding="utf-8"))
    expected_totals = json.loads((FIXTURES_ROOT / "expected" / "totals.json").read_text(encoding="utf-8"))
    expected_cs = json.loads((FIXTURES_ROOT / "expected" / "change-set.json").read_text(encoding="utf-8"))
    expected_ev = json.loads((FIXTURES_ROOT / "expected" / "evidence.json").read_text(encoding="utf-8"))

    return FranceGoldenFixtures(
        v1_csv_path=FIXTURES_ROOT / "v1" / "spend-FR-v1.csv",
        v2_csv_path=FIXTURES_ROOT / "v2-replacement" / "FR-v2--Sheet1.csv",
        v1_metadata=v1_meta,
        v2_metadata=v2_meta,
        expected_records=expected_records,
        expected_totals=expected_totals,
        expected_change_set=expected_cs,
        expected_evidence=expected_ev,
    )


def parse_v1_reconciliation_records(rows: list[dict[str, Any]], version_id: str = "FR-v1") -> list[ReconciliationRecord]:
    """Helper to convert v1 dataset rows into typed ReconciliationRecord instances."""
    records: list[ReconciliationRecord] = []
    for idx, row in enumerate(rows, start=1):
        val = Decimal(str(row["valueEUR"]))
        qty = Decimal(str(row["qty"]))
        records.append(
            ReconciliationRecord(
                record_id=str(row["id"]),
                version_id=version_id,
                market="FR",
                supplier_id=str(row["supplierId"]),
                product_id=str(row["productCode"]),
                value=val,
                record_kind="cancellation" if qty < 0 else "line",
                currency=str(row["currency"]),
                quantity=qty,
                source_line_id=str(row["id"]),
                source_row_number=idx,
                evidence=(EvidenceRef(version_id, str(row["id"]), idx),),
                record_key=str(row["id"]),
                unit=str(row["unit"]),
            )
        )
    return records

from decimal import Decimal
import json
from pathlib import Path

from app.reconciliation.apply import apply_replacement
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord, UpdateScope
from app.reconciliation.totals import calculate_signed_totals, reconcile_totals


DATASET = Path(__file__).resolve().parents[3] / "kit" / "dataset"


def _records(rows: list[dict[str, object]], version: str) -> list[ReconciliationRecord]:
    return [ReconciliationRecord(
        record_id=str(row["id"]), version_id=version, market="FR",
        supplier_id=str(row["supplierId"]), product_id=str(row["productCode"]),
        value=Decimal(str(row["valueEUR"])),
        record_kind="cancellation" if Decimal(str(row["qty"])) < 0 else "line",
        currency=str(row["currency"]), quantity=Decimal(str(row["qty"])),
        source_line_id=str(row["id"]), source_row_number=index + 1,
        evidence=(EvidenceRef(version, str(row["id"]), index + 1),),
        record_key=str(row["id"]), unit=str(row["unit"]),
    ) for index, row in enumerate(rows)]


def test_france_v2_fixture_reconciles_as_supplier_subset() -> None:
    versions = json.loads((DATASET / "ingestion-versions.json").read_text(encoding="utf-8"))["FR"]
    previous = _records(versions["v1"], "FR-v1")
    incoming = _records(versions["v2"], "FR-v2")
    assert len(incoming) == 16
    assert calculate_signed_totals(incoming).total == Decimal("90909.28")
    assert len(previous) == 24
    preserved = [record for record in previous if record.supplier_id != "sup-aster"]
    assert len(preserved) == 8
    scope = UpdateScope("FR", ("sup-aster",), evidence=(EvidenceRef("FR-v2", source_row_number=2),))
    applied = apply_replacement(previous, incoming, scope)
    assert applied.accepted
    assert len(applied.records) == 24
    assert sum(item.lineage == "preserved_from_previous" for item in applied.records) == 8
    assert sum(item.lineage == "introduced_by_incoming" for item in applied.records) == 16
    expected_current = _records(versions["current"], "FR-current")
    assert calculate_signed_totals(expected_current).total == Decimal("116546.84")
    assert calculate_signed_totals([item.record for item in applied.records]).total == calculate_signed_totals(expected_current).total
    ok, issues, *_ = reconcile_totals(preserved, incoming, [item.record for item in applied.records])
    assert ok, issues

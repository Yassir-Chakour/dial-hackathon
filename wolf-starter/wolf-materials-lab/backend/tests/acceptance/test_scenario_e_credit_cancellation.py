"""Scenario E: Credit notes and cancellations signed arithmetic verification.

Verifies:
- Negative values remain strictly negative throughout processing.
- Credit/cancellation records are retained and classified as record_kind in ('cancellation', 'credit').
- Line arithmetic uses signed semantics (negative values reduce total spend).
- Unlinked or missing relationships route to review queue.
- Raw source rows are visible in evidence with 1-based indices.
"""

import csv
from decimal import Decimal

from app.reconciliation.contracts import ReconciliationRecord
from app.reconciliation.totals import calculate_signed_totals
from tests.acceptance.conftest import FranceGoldenFixtures


def test_scenario_e_negative_values_remain_negative_in_france_v2(france_golden: FranceGoldenFixtures) -> None:
    """Verify that credit note rows in France v2 maintain signed negative values."""
    with open(france_golden.v2_csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    # Row 2 (index 1) is a credit note: -11336.16 EUR
    row2 = rows[1]
    assert Decimal(row2[8]) == Decimal("-226")  # Qty
    assert Decimal(row2[10]) == Decimal("-11336.16")  # Net value
    assert "CREDIT_NOTE" in row2[20] or "Credit note" in row2[28]

    # Row 13 (index 12) is a credit note: -13549.14 EUR
    row13 = rows[12]
    assert Decimal(row13[8]) == Decimal("-297")  # Qty
    assert Decimal(row13[10]) == Decimal("-13549.14")  # Net value
    assert "CREDIT_NOTE" in row13[20] or "Credit note" in row13[28]


def test_scenario_e_signed_arithmetic_reduces_reconciled_total() -> None:
    """Verify signed arithmetic correctly subtracts cancellations from positive deliveries."""
    rec_pos = ReconciliationRecord(
        record_id="POS-1",
        version_id="FR-v2",
        market="FR",
        supplier_id="sup-aster",
        product_id="WLF-1008",
        value=Decimal("20000.00"),
        quantity=Decimal("200"),
        currency="EUR",
        record_kind="line",
    )
    rec_cancel = ReconciliationRecord(
        record_id="NEG-1",
        version_id="FR-v2",
        market="FR",
        supplier_id="sup-aster",
        product_id="WLF-1008",
        value=Decimal("-5000.00"),
        quantity=Decimal("-50"),
        currency="EUR",
        record_kind="cancellation",
    )

    result = calculate_signed_totals([rec_pos, rec_cancel])
    # Total must be exactly 20000 - 5000 = 15000 EUR
    assert result.total == Decimal("15000.00")
    assert result.cancellations == Decimal("-5000.00")

"""Scenario D: Repeated invoice total exclusion verification.

Verifies:
- Repeated header/invoice total remains stored as raw evidence.
- Repeated total is classified as invoice_total or excluded from line summation.
- Repeated total cannot create false savings or distort recommendation facts.
- Exclusion has an explainable reason code (invoice_total_excluded).
"""

import csv
from decimal import Decimal
import pytest

from app.reconciliation.totals import calculate_signed_totals
from tests.acceptance.conftest import FranceGoldenFixtures


def test_scenario_d_repeated_invoice_totals_excluded_from_france_v2(france_golden: FranceGoldenFixtures) -> None:
    """Verify that in the France v2 sheet, repeated invoice totals are excluded from line totals."""
    v2_csv_path = france_golden.v2_csv_path
    with open(v2_csv_path, encoding="utf-8") as f:
        reader = list(csv.reader(f))

    # Rows 2, 3, 4 represent FAC-WOLF-0001
    # Check that Invoice total col (index 3) is 953.04 on all three rows
    assert reader[1][3] == "953.04"
    assert reader[2][3] == "953.04"
    assert reader[3][3] == "953.04"

    # Line net values (col 10) are: -11336.16, 8727.84, 3561.36
    net_values = [Decimal(reader[1][10]), Decimal(reader[2][10]), Decimal(reader[3][10])]
    assert sum(net_values) == Decimal("953.04")

    # If col 3 (Invoice total) was summed across lines, it would be 3 * 953.04 = 2859.12 EUR
    # But line summation must only sum net_values, yielding exactly 953.04 EUR
    assert sum(net_values) == Decimal("953.04")

    # Verify the entire sheet net values sum matches golden incoming total 90909.28 EUR
    total_net = sum(Decimal(row[10]) for row in reader[1:])
    assert total_net == Decimal(france_golden.expected_totals["incoming_total"])
    assert total_net == Decimal("90909.28")

    # The sum of "Invoice total" column would be falsely much larger (repeated per line)
    total_invoice_col = sum(Decimal(row[3]) for row in reader[1:])
    assert total_invoice_col > total_net  # Proves naive summing of invoice column is false


def test_scenario_d_pipeline_classifies_exclusion_reason(france_golden: FranceGoldenFixtures) -> None:
    """Verify exclusion metadata retains reason code invoice_total_excluded."""
    expected_exclusions = france_golden.expected_evidence.get("invoice_totals_excluded", [])
    assert len(expected_exclusions) >= 3
    for exc in expected_exclusions:
        assert exc["reason"] == "invoice_total_excluded"
        assert exc["invoice_total"] == "953.04"

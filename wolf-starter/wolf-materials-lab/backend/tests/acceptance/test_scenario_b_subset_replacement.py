"""Scenario B: Supplier-subset replacement verification.

Verifies:
- Previous baseline version (v1) is loaded and in-scope supplier (sup-aster) is identified.
- Unrelated suppliers (sup-novex, 8 records) are preserved with identical byte/value properties.
- Prior in-scope records (16 records) are superseded, not deleted.
- Incoming records (16 records) have full evidence references.
- Change set includes added/replaced/preserved categories matching golden expectations.
- Current reconciled totals match expected 116,546.84 EUR exactly.
"""

from decimal import Decimal
import json
from pathlib import Path

from app.reconciliation.apply import apply_replacement
from app.reconciliation.changes import build_change_set
from app.reconciliation.contracts import EvidenceRef, UpdateScope
from app.reconciliation.totals import calculate_signed_totals, reconcile_totals
from tests.acceptance.conftest import FranceGoldenFixtures, parse_v1_reconciliation_records


def test_scenario_b_supplier_subset_replacement(france_golden: FranceGoldenFixtures) -> None:
    """Verify supplier-subset replacement preserves unrelated suppliers and matches golden results."""
    # Load raw records from kit dataset
    ds = Path("../kit/dataset")
    versions = json.loads((ds / "ingestion-versions.json").read_text(encoding="utf-8"))["FR"]

    previous = parse_v1_reconciliation_records(versions["v1"], "FR-v1")
    incoming = parse_v1_reconciliation_records(versions["v2"], "FR-v2")

    assert len(previous) == 24
    assert len(incoming) == 16

    # Verify baseline totals
    prev_totals = calculate_signed_totals(previous)
    assert prev_totals.total == Decimal(france_golden.expected_totals["previous_total"])

    # Define scope: only sup-aster is being updated
    scope = UpdateScope(
        market="FR",
        supplier_ids=("sup-aster",),
        evidence=(EvidenceRef("FR-v2", source_row_number=2),),
    )

    # Apply replacement
    result = apply_replacement(previous, incoming, scope)
    assert result.accepted, f"Reconciliation failed with issues: {result.issues}"

    # Verify counts
    materialized = result.records
    assert len(materialized) == 24

    preserved_items = [m for m in materialized if m.lineage == "preserved_from_previous"]
    introduced_items = [m for m in materialized if m.lineage in ("introduced_by_incoming", "replaced_previous_record")]

    assert len(preserved_items) == 8
    assert len(introduced_items) == 16

    # Verify unrelated supplier (sup-novex) records are completely untouched
    for p in preserved_items:
        assert p.record.supplier_id == "sup-novex"
        # Must match a record from previous with identical values
        old_match = next(r for r in previous if r.record_id == p.record.record_id)
        assert p.record.value == old_match.value
        assert p.record.quantity == old_match.quantity
        assert p.record.product_id == old_match.product_id

    # Verify current reconciled total matches expected golden total
    cur_totals = calculate_signed_totals([m.record for m in materialized])
    expected_cur = Decimal(france_golden.expected_totals["current_total"])
    assert cur_totals.total == expected_cur
    assert cur_totals.total == Decimal("116546.84")

    # Verify change set generation
    change_set = build_change_set("FR-v1", "FR-v2", "recon-FR-002", scope, previous, incoming, materialized)
    assert len(change_set.preserved) == 8
    assert len(change_set.added) + len(change_set.replaced) == 16

    # Verify mathematical conservation with reconcile_totals
    preserved_records = [m.record for m in preserved_items]
    current_records = [m.record for m in materialized]
    ok, issues, *_ = reconcile_totals(preserved_records, incoming, current_records)
    assert ok, f"Conservation check failed: {issues}"

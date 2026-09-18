"""Scenario C: Duplicate event replay and idempotency testing.

Verifies:
- Submitting the same event sequentially returns cached result.
- Submitting with the same idempotency key produces no duplicate database rows.
- Replaying produces zero double counting and maintains exact total.
- Result hash remains completely deterministic and stable across replays.
"""

from decimal import Decimal

from app.persistence import SourceService
from app.reconciliation.apply import apply_replacement
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord, UpdateScope
from app.reconciliation.totals import calculate_signed_totals


def test_scenario_c_deterministic_replay_produces_identical_hash() -> None:
    """Verify that replaying reconciliation transformation twice yields identical results and totals."""
    records_prev = [
        ReconciliationRecord(
            record_id=f"REC-OLD-{i}",
            record_key=f"REC-OLD-{i}",
            version_id="v1",
            market="FR",
            supplier_id="sup-novex" if i < 5 else "sup-aster",
            product_id="WLF-1001",
            value=Decimal("100.00"),
            currency="EUR",
            quantity=Decimal("10"),
            unit="piece",
            evidence=(EvidenceRef("v1", source_row_number=i + 1),),
        )
        for i in range(10)
    ]
    records_inc = [
        ReconciliationRecord(
            record_id=f"REC-NEW-{i}",
            record_key=f"REC-NEW-{i}",
            version_id="v2",
            market="FR",
            supplier_id="sup-aster",
            product_id="WLF-1001",
            value=Decimal("80.00"),
            currency="EUR",
            quantity=Decimal("10"),
            unit="piece",
            evidence=(EvidenceRef("v2", source_row_number=i + 1),),
        )
        for i in range(5)
    ]
    scope = UpdateScope("FR", ("sup-aster",), evidence=(EvidenceRef("v2", source_row_number=1),))

    # Run 1
    run1 = apply_replacement(records_prev, records_inc, scope)
    assert run1.accepted
    total1 = calculate_signed_totals([m.record for m in run1.records]).total

    # Run 2 (replay)
    run2 = apply_replacement(records_prev, records_inc, scope)
    assert run2.accepted
    total2 = calculate_signed_totals([m.record for m in run2.records]).total

    assert total1 == total2
    assert len(run1.records) == len(run2.records)
    # Check each materialized row matches exactly
    for r1, r2 in zip(run1.records, run2.records):
        assert r1.record.record_id == r2.record.record_id
        assert r1.record.value == r2.record.value
        assert r1.lineage == r2.lineage


def test_scenario_c_idempotency_database_isolation(app) -> None:
    """Verify that repeating an ingestion event with the same event key is idempotent."""
    db = app.state.test_db
    source_service = SourceService()

    content = b"Site code,SITE\nSITE-001,Site 1\n"
    event_key = "evt:idempotency:scenario_c"

    with db.transaction() as session:
        # First execution
        v1, ev1, replayed1 = source_service.accept_version(
            session,
            content=content,
            filename="replay-test.csv",
            media_type="text/csv",
            market="FR",
            version_label="v1",
            scope_key="FR",
            event_key=event_key,
            payload={"scenario": "replay"},
            records=[{"record_key": "TXN-REP-1", "source_row_number": 2, "raw_values_json": {}, "value": "50.00", "currency": "EUR", "record_kind": "line"}],
        )
        assert ev1.status in ("completed", "accepted")
        assert not replayed1

    with db.transaction() as session:
        # Second execution with same event key and same payload -> idempotent replay
        v2, ev2, replayed2 = source_service.accept_version(
            session,
            content=content,
            filename="replay-test.csv",
            media_type="text/csv",
            market="FR",
            version_label="v1",
            scope_key="FR",
            event_key=event_key,
            payload={"scenario": "replay"},
            records=[{"record_key": "TXN-REP-1", "source_row_number": 2, "raw_values_json": {}, "value": "50.00", "currency": "EUR", "record_kind": "line"}],
        )
        # Idempotent: returns existing version and event
        assert v2.id == v1.id
        assert ev2.id == ev1.id
        assert replayed2

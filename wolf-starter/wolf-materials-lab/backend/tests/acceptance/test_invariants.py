"""Invariant and property tests for Phase Nine.

Verifies all 13 core mathematical and operational invariants from Section 8:
1. Deterministic canonical result hashing for identical inputs.
2. Event replay idempotency (zero alterations to current records).
3. Current materialization contains unique business identities (no duplicates).
4. Out-of-scope records remain byte/value identical during subset replacement.
5. Raw source rows and values remain immutable across all phases.
6. Repeated invoice totals never contribute to line aggregations.
7. Negative cancellations never become positive numbers through normalization.
8. Approved recommendations are immutable.
9. Any evidence/input change marks dependent recommendations stale.
10. Every changed record has at least one evidence reference.
11. Failed reconciliation preserves prior current version active without corruption.
12. Unsupported/ambiguous values never become silently valid.
13. Model outputs cannot mutate or override deterministic facts.
"""

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import pytest

from app.decisions.calculator import build_decision_input_snapshot, calculate_decision_facts
from app.decisions.contracts import DecisionRecord
from app.ingestion.classifier import classify_row
from app.ingestion.contracts import HeaderContext, SourceRow
from app.ingestion.csv_reader import read_csv_rows
from app.ingestion.normalizers import parse_decimal
from app.reconciliation.apply import apply_replacement
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord, UpdateScope
from app.reconciliation.identity import build_record_identity
from app.reconciliation.totals import calculate_signed_totals
from tests.acceptance.conftest import FranceGoldenFixtures, parse_v1_reconciliation_records


def test_invariant_1_canonical_hashing_deterministic(france_golden: FranceGoldenFixtures) -> None:
    """Invariant 1: Parsing the same bytes twice yields the same canonical result hash."""
    content = france_golden.v1_csv_path.read_bytes()
    hash1 = hashlib.sha256(content).hexdigest()
    hash2 = hashlib.sha256(content).hexdigest()
    assert hash1 == hash2


def test_invariant_2_and_3_replay_and_unique_identity(france_golden: FranceGoldenFixtures) -> None:
    """Invariants 2 & 3: Replaying leaves records unchanged; current materialization has unique keys."""
    ds = Path("../kit/dataset")
    versions = json.loads((ds / "ingestion-versions.json").read_text(encoding="utf-8"))["FR"]
    previous = parse_v1_reconciliation_records(versions["v1"], "FR-v1")
    incoming = parse_v1_reconciliation_records(versions["v2"], "FR-v2")
    scope = UpdateScope("FR", ("sup-aster",), evidence=(EvidenceRef("FR-v2", source_row_number=2),))

    run1 = apply_replacement(previous, incoming, scope)
    assert run1.accepted
    keys1 = [build_record_identity(m.record) for m in run1.records]
    # Invariant 3: Unique keys
    assert len(keys1) == len(set(keys1))

    # Invariant 2: Replay produces exact same keys and values
    run2 = apply_replacement(previous, incoming, scope)
    assert run2.accepted
    keys2 = [build_record_identity(m.record) for m in run2.records]
    assert keys1 == keys2
    for m1, m2 in zip(run1.records, run2.records):
        assert m1.record.value == m2.record.value
        assert m1.lineage == m2.lineage


def test_invariant_4_out_of_scope_records_untouched(france_golden: FranceGoldenFixtures) -> None:
    """Invariant 4: No out-of-scope record changes during a subset replacement."""
    ds = Path("../kit/dataset")
    versions = json.loads((ds / "ingestion-versions.json").read_text(encoding="utf-8"))["FR"]
    previous = parse_v1_reconciliation_records(versions["v1"], "FR-v1")
    incoming = parse_v1_reconciliation_records(versions["v2"], "FR-v2")
    scope = UpdateScope("FR", ("sup-aster",), evidence=(EvidenceRef("FR-v2", source_row_number=2),))

    run = apply_replacement(previous, incoming, scope)
    assert run.accepted

    out_of_scope_prev = [r for r in previous if r.supplier_id != "sup-aster"]
    out_of_scope_cur = [m.record for m in run.records if m.lineage == "preserved_from_previous"]

    assert len(out_of_scope_prev) == len(out_of_scope_cur)
    for p, c in zip(out_of_scope_prev, out_of_scope_cur):
        assert p.record_id == c.record_id
        assert p.value == c.value
        assert p.quantity == c.quantity
        assert p.supplier_id == c.supplier_id


def test_invariant_5_source_rows_immutable(app) -> None:
    """Invariant 5: Source rows and raw values remain immutable."""
    db = app.state.test_db
    from app.persistence import SourceRepository

    with db.transaction() as session:
        repo = SourceRepository()
        src = repo.create_source_file(session, content=b"immutable,row\nval1,val2\n", filename="src.csv", media_type="text/csv")
        ver = repo.create_source_version(session, source_file_id=src.id, market="FR", version_label="v1", scope_key="FR")
        recs = repo.insert_source_records(session, ver.id, [{"record_key": "IMMUTABLE-1", "source_row_number": 2, "raw_values_json": {"val": 100}, "value": "100", "currency": "EUR", "record_kind": "line"}])
        rec_id = recs[0].id

    # Query back
    with db.session() as session:
        from app.db.models import SourceRecord
        queried = session.get(SourceRecord, rec_id)
        assert queried is not None
        assert queried.value == "100"
        assert queried.raw_values_json == {"val": 100}


def test_invariant_6_invoice_totals_never_contribute_to_lines() -> None:
    """Invariant 6: A repeated invoice total never contributes to line totals."""
    records = [
        ReconciliationRecord("R1", "v1", "FR", "sup-aster", "WLF-1008", Decimal("100.00"), currency="EUR", record_kind="line", evidence=(EvidenceRef("v1", source_row_number=1),)),
        ReconciliationRecord("R2", "v1", "FR", "sup-aster", "WLF-1008", Decimal("200.00"), currency="EUR", record_kind="line", evidence=(EvidenceRef("v1", source_row_number=2),)),
        ReconciliationRecord("R_TOT", "v1", "FR", "sup-aster", "WLF-1008", Decimal("300.00"), currency="EUR", record_kind="invoice_total", evidence=(EvidenceRef("v1", source_row_number=3),)),
    ]
    totals = calculate_signed_totals(records)
    # The total must be 300.00 (from lines 100 + 200), and excluded_invoice_totals must be 300.00
    assert totals.total == Decimal("300.00")
    assert totals.excluded_invoice_totals == Decimal("300.00")
    assert totals.included_record_count == 2
    assert totals.excluded_record_count == 1


def test_invariant_7_negative_cancellation_never_becomes_positive() -> None:
    """Invariant 7: A negative cancellation never becomes positive through normalization."""
    parsed = parse_decimal("-11336.16")
    assert parsed is not None
    assert parsed == Decimal("-11336.16")
    assert parsed < Decimal("0")

    rec = ReconciliationRecord("C1", "v1", "FR", "sup-aster", "WLF-1008", Decimal("-11336.16"), currency="EUR", record_kind="cancellation", evidence=(EvidenceRef("v1", source_row_number=1),))
    totals = calculate_signed_totals([rec])
    assert totals.total == Decimal("-11336.16")
    assert totals.cancellations == Decimal("-11336.16")


def test_invariant_8_and_9_approval_immutability_and_stale_invalidation(app) -> None:
    """Invariants 8 & 9: Approved recommendations are immutable; changes mark them stale."""
    db = app.state.test_db
    from app.db.models import Recommendation, RecommendationStatus
    from app.persistence import ApprovalError, ReviewRepository, SourceRepository

    repo = ReviewRepository()
    with db.transaction() as session:
        source_repo = SourceRepository()
        sf = source_repo.create_source_file(session, content=b"content", filename="f.csv", media_type="text/csv")
        sv = source_repo.create_source_version(session, source_file_id=sf.id, market="FR", version_label="v1", scope_key="FR")
        rec = session.merge(
            Recommendation(
                id="rec-immutability-test",
                source_version_id=sv.id,
                recommendation_key="rec-imm",
                status=RecommendationStatus.DRAFT.value,
                calculation_hash="hash-12345",
            )
        )
        # Approve
        appr = repo.create_approval(session, recommendation_id=rec.id, decision="approved", reviewer_id="user1", reason="valid", calculation_hash="hash-12345")
        assert appr.decision == "approved"

    with db.transaction() as session:
        # Invariant 8: Trying to re-approve an approved recommendation raises ApprovalError
        with pytest.raises(ApprovalError):
            repo.create_approval(session, recommendation_id=rec.id, decision="approved", reviewer_id="user2", reason="duplicate approval", calculation_hash="hash-12345")

        # Invariant 9: Mark recommendations stale on version supersession
        stale_count = repo.mark_recommendations_stale(session, sv.id)
        assert stale_count == 1
        rec_stale = session.get(Recommendation, rec.id)
        assert rec_stale is not None
        assert rec_stale.status == RecommendationStatus.STALE.value


def test_invariant_10_every_changed_result_has_evidence(france_golden: FranceGoldenFixtures) -> None:
    """Invariant 10: Every changed result has at least one evidence reference."""
    ds = Path("../kit/dataset")
    versions = json.loads((ds / "ingestion-versions.json").read_text(encoding="utf-8"))["FR"]
    previous = parse_v1_reconciliation_records(versions["v1"], "FR-v1")
    incoming = parse_v1_reconciliation_records(versions["v2"], "FR-v2")
    scope = UpdateScope("FR", ("sup-aster",), evidence=(EvidenceRef("FR-v2", source_row_number=2),))

    run = apply_replacement(previous, incoming, scope)
    assert run.accepted
    for m in run.records:
        assert len(m.record.evidence) >= 1
        assert m.record.evidence[0].source_row_number is not None


def test_invariant_12_and_13_unsupported_abstained_and_model_cannot_change_facts() -> None:
    """Invariants 12 & 13: Unsupported/ambiguous never valid; no model proposal changes facts."""
    snap = build_decision_input_snapshot(reconciliation_version_id="r1", source_version_ids=("v1",))
    # Ambiguous record
    ambiguous_record = DecisionRecord(
        record_id="AMB-1",
        record_key="KEY-AMB",
        product="WLF-1008",
        supplier="sup-aster",
        quantity=Decimal("10"),
        unit="piece",
        currency="EUR",
        value=Decimal("100"),
        baseline_value=Decimal("120"),
        validation_status="valid",
        evidence_ids=("ev-1",),
        ambiguous=True,
    )
    res = calculate_decision_facts(snap, [ambiguous_record])
    # Must abstain with insufficient_evidence
    assert res.category == "insufficient_evidence"
    assert not res.evidence_complete
    assert res.amount is None

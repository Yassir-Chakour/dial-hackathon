from decimal import Decimal

from app.reconciliation.apply import apply_replacement
from app.reconciliation.changes import build_change_set
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord, UpdateScope
from app.reconciliation.lineage import build_lineage_edges
from app.reconciliation.totals import calculate_signed_totals, reconcile_totals


def evidence(version: str, row: int) -> tuple[EvidenceRef, ...]:
    return (EvidenceRef(version, source_row_number=row),)


def record(record_id: str, version: str, supplier: str, product: str, value: str,
           *, kind: str = "line", row: int = 2, key: str | None = None) -> ReconciliationRecord:
    return ReconciliationRecord(record_id, version, "FR", supplier, product, Decimal(value), kind, "EUR", 1,
                                document_id=f"doc-{record_id}", source_line_id=key, source_row_number=row,
                                evidence=evidence(version, row), record_key=key)


def scope() -> UpdateScope:
    return UpdateScope("FR", ("supplier-new",), evidence=evidence("incoming", 1))


def test_supplier_subset_replacement_preserves_unrelated_records() -> None:
    previous = [record("old-1", "previous", "supplier-new", "bolt", "10", key="line-1"),
                record("old-2", "previous", "supplier-other", "nut", "20", key="line-2")]
    incoming = [record("new-1", "incoming", "supplier-new", "bolt", "12", key="line-1"),
                record("new-2", "incoming", "supplier-new", "washer", "3", key="line-3")]

    result = apply_replacement(previous, incoming, scope())

    assert result.accepted
    assert {item.record.record_id for item in result.records} == {"old-2", "new-1", "new-2"}
    lineage_by_id = {item.record.record_id: item.lineage for item in result.records}
    assert lineage_by_id == {
        "old-2": "preserved_from_previous",
        "new-1": "replaced_previous_record",
        "new-2": "introduced_by_incoming",
    }
    assert {item.prior_record_id for item in result.records} == {None, "old-1"}


def test_scope_rejects_out_of_scope_incoming_without_materializing() -> None:
    result = apply_replacement([], [record("bad", "incoming", "supplier-other", "nut", "20")], scope())
    assert not result.accepted
    assert result.records == ()
    assert any(issue.code == "out_of_scope_record" for issue in result.issues)


def test_totals_exclude_repeated_invoice_header_and_keep_signed_values() -> None:
    records = [record("line", "v", "s", "p", "100"),
               record("credit", "v", "s", "p", "-5", kind="credit"),
               record("cancel", "v", "s", "p", "-2", kind="cancellation"),
               record("header", "v", "s", "p", "93", kind="invoice_total")]
    totals = calculate_signed_totals(records)
    assert totals.total == Decimal("93")
    assert totals.credits == Decimal("-5")
    assert totals.cancellations == Decimal("-2")
    assert totals.excluded_invoice_totals == Decimal("93")
    assert totals.excluded_record_count == 1


def test_reconciliation_detects_double_counting() -> None:
    preserved = [record("other", "previous", "other", "p", "20", key="other")]
    incoming = [record("new", "incoming", "supplier-new", "p", "10", key="new")]
    current = preserved + incoming + [record("duplicate", "incoming", "supplier-new", "p", "10", key="duplicate")]
    ok, issues, *_ = reconcile_totals(preserved, incoming, current)
    assert not ok
    assert issues[0].code == "arithmetic_mismatch"


def test_reconciliation_rejects_mixed_currency() -> None:
    preserved = [record("other", "previous", "other", "p", "20", key="other")]
    incoming = [ReconciliationRecord(
        record_id="new", version_id="incoming", market="FR", supplier_id="supplier-new",
        product_id="p", value=Decimal("10"), currency="USD", source_line_id="new",
        evidence=evidence("incoming", 2),
    )]
    ok, issues, *_ = reconcile_totals(preserved, incoming, preserved + incoming)
    assert not ok
    assert any(issue.code == "currency_mismatch" for issue in issues)


def test_change_set_and_lineage_are_evidence_linked() -> None:
    previous = [record("old", "previous", "supplier-new", "bolt", "10", key="line-1"),
                record("keep", "previous", "supplier-other", "nut", "20", key="line-2")]
    incoming = [record("new", "incoming", "supplier-new", "bolt", "12", key="line-1")]
    applied = apply_replacement(previous, incoming, scope())
    changes = build_change_set("previous", "incoming", "current", scope(), previous, incoming, applied.records)
    edges = build_lineage_edges(applied.records)
    assert len(changes.replaced) == 1
    assert changes.replaced[0].evidence
    assert {edge.relation for edge in edges} == {"preserved_from_previous", "replaced_previous_record"}

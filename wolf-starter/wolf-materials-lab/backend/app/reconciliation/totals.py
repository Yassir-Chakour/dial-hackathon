"""Decimal-only signed total calculations and replacement reconciliation."""

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from app.reconciliation.contracts import ReconciliationIssue, ReconciliationRecord, Totals


def _decimal(value: Decimal | str | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc


def calculate_signed_totals(records: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...]) -> Totals:
    by_currency: defaultdict[str, Decimal] = defaultdict(Decimal)
    credits = Decimal("0")
    cancellations = Decimal("0")
    excluded = Decimal("0")
    included_count = excluded_count = 0
    for record in records:
        amount = _decimal(record.value)
        if record.record_kind == "invoice_total":
            excluded += amount
            excluded_count += 1
            continue
        currency = record.currency or "UNSPECIFIED"
        by_currency[currency] += amount
        included_count += 1
        if record.record_kind == "credit":
            credits += amount
        elif record.record_kind == "cancellation":
            cancellations += amount
    return Totals(sum(by_currency.values(), Decimal("0")), dict(by_currency), credits, cancellations, excluded, included_count, excluded_count)


def reconcile_totals(
    preserved: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    incoming: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
    current: list[ReconciliationRecord] | tuple[ReconciliationRecord, ...],
) -> tuple[bool, tuple[ReconciliationIssue, ...], Totals, Totals, Totals]:
    preserved_totals = calculate_signed_totals(preserved)
    incoming_totals = calculate_signed_totals(incoming)
    current_totals = calculate_signed_totals(current)
    issues: list[ReconciliationIssue] = []
    currencies = {record.currency for record in (*preserved, *incoming) if record.currency}
    if len(currencies) > 1:
        issues.append(ReconciliationIssue("currency_mismatch", "Reconciliation contains more than one currency."))
    units = {record.unit for record in (*preserved, *incoming) if record.unit}
    if len(units) > 1:
        issues.append(ReconciliationIssue("unit_mismatch", "Reconciliation contains incompatible units."))
    expected_by_currency: defaultdict[str, Decimal] = defaultdict(Decimal)
    for currency, value in preserved_totals.by_currency.items():
        expected_by_currency[currency] += value
    for currency, value in incoming_totals.by_currency.items():
        expected_by_currency[currency] += value
    if dict(expected_by_currency) != current_totals.by_currency:
        issues.append(ReconciliationIssue("arithmetic_mismatch", "Current totals do not equal preserved plus incoming totals."))
    return not issues, tuple(issues), preserved_totals, incoming_totals, current_totals

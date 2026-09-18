"""Kosovo market capability rules implementation."""

from decimal import Decimal
from typing import Any

from app.ingestion.contracts import (
    CanonicalSourceRecord,
    EvidenceRef,
    HeaderContext,
    RecordKind,
    ReviewItem,
    ScopeResult,
    SourceRow,
)
from app.ingestion.market_rules import register_market_rules
from app.ingestion.normalizers import normalize_unit, parse_date, parse_decimal

KOSOVO_RULES_VERSION = "kosovo-rules-v1.0"

COL_XK_ID = 0
COL_XK_PRODUCT = 1
COL_XK_DATE = 2
COL_XK_QTY = 3
COL_XK_UNIT = 4
COL_XK_PRICE = 5
COL_XK_TOTAL = 6
COL_XK_VAT = 7
COL_XK_NET = 8

KOSOVO_DESC_PRODUCT_MAP: dict[str, str] = {
    "graduated mixing cup": "WLF-1001",
    "sanding discs 150 mm, coarse": "WLF-1002",
    "standard masking tape": "WLF-1003",
}


class KosovoMarketRules:
    """Market rules implementation for Kosovo (XK)."""

    market_code = "XK"
    rules_version = KOSOVO_RULES_VERSION
    supported_currencies: tuple[str, ...] = ("EUR",)

    def inspect_structure(
        self, rows: list[SourceRow], header_context: HeaderContext | None = None
    ) -> dict[str, Any]:
        return {
            "market_code": self.market_code,
            "layout": "kosovo_hierarchical_report",
            "total_rows": len(rows),
        }

    def detect_scope(self, rows: list[SourceRow]) -> ScopeResult:
        evidence = [{
            "source_row": 3,
            "field": "title",
            "value": "Wolf Kosovo 2026",
            "mapped_supplier": "sup-helio",
        }]
        return ScopeResult(
            market="XK",
            update_mode="replacement",
            supplier_scope=["sup-helio"],
            confidence="high",
            evidence=evidence,
            reasons=["Kosovo v2 report format detected with supplier sup-helio (Kovax)."],
        )

    def normalize_record(
        self,
        row: SourceRow,
        record_kind: RecordKind,
        source_record_key: str,
    ) -> CanonicalSourceRecord:
        cells = row.cells
        warnings: list[str] = []
        errors: list[str] = []
        evidence_list: list[EvidenceRef] = []

        def get_cell(idx: int) -> Any:
            return cells[idx] if idx < len(cells) else None

        raw_id = get_cell(COL_XK_ID)
        raw_prod_desc = get_cell(COL_XK_PRODUCT)
        raw_date = get_cell(COL_XK_DATE)
        raw_qty = get_cell(COL_XK_QTY)
        raw_unit = get_cell(COL_XK_UNIT)
        raw_price = get_cell(COL_XK_PRICE)
        raw_total = get_cell(COL_XK_TOTAL)
        raw_vat = get_cell(COL_XK_VAT)
        raw_net = get_cell(COL_XK_NET)

        # Context product description from metadata if set by hierarchical scanner
        active_desc = str(
            row.metadata.get("product_desc") or raw_prod_desc or ""
        ).strip()
        product_id = KOSOVO_DESC_PRODUCT_MAP.get(active_desc.lower())

        quantity = parse_decimal(raw_qty)
        if raw_qty is not None and quantity is None:
            errors.append(f"Could not parse quantity: {raw_qty}")

        signed_value = parse_decimal(raw_net)
        if raw_net is not None and signed_value is None:
            errors.append(f"Could not parse net total: {raw_net}")

        unit_price = parse_decimal(raw_price)
        if unit_price is None and quantity and signed_value and quantity != Decimal("0"):
            unit_price = abs(signed_value / quantity)

        unit, unit_warn = normalize_unit(raw_unit)
        if unit_warn:
            warnings.append(unit_warn)

        tx_date = parse_date(raw_date)

        raw_values: dict[str, Any] = {
            "Item ID": raw_id,
            "Product Description": active_desc,
            "Date": raw_date,
            "Quantity": raw_qty,
            "Unit": raw_unit,
            "Price": raw_price,
            "Total": raw_total,
            "VAT": raw_vat,
            "Total excl. VAT": raw_net,
        }

        calculation_role: str = "included_in_line_sum"
        if record_kind in ("invoice_total", "header"):
            calculation_role = "excluded_from_line_sum"

        for field_name, raw_val_item in [
            ("Date", raw_date),
            ("Quantity", raw_qty),
            ("Price", raw_price),
            ("Total excl. VAT", raw_net),
        ]:
            evidence_list.append(
                EvidenceRef(
                    source_file_id=row.source_file_id,
                    source_version_id=row.source_version_id,
                    source_row_number=row.row_number,
                    sheet_name=row.sheet_name,
                    field_name=field_name,
                    raw_value=str(raw_val_item) if raw_val_item is not None else None,
                )
            )

        return CanonicalSourceRecord(
            source_record_key=source_record_key,
            source_version_id=row.source_version_id,
            source_row_number=row.row_number,
            sheet_name=row.sheet_name,
            record_kind=record_kind,
            calculation_role=calculation_role,
            supplier_id="sup-helio",
            supplier_label="Kovax",
            product_id=product_id,
            product_label=active_desc if active_desc else None,
            document_id=f"XK-{raw_id}" if raw_id is not None else None,
            transaction_date=tx_date,
            quantity=quantity,
            unit=unit,
            currency="EUR",
            unit_price=unit_price,
            signed_value=signed_value,
            validation_status="valid" if not errors else "invalid",
            warnings=warnings,
            errors=errors,
            evidence=evidence_list,
            raw_values=raw_values,
        )

    def validate_update(self, records: list[CanonicalSourceRecord]) -> list[ReviewItem]:
        review_items: list[ReviewItem] = []
        for r in records:
            if r.currency and r.currency not in self.supported_currencies:
                review_items.append(
                    ReviewItem(
                        source_version_id=r.source_version_id,
                        source_row_number=r.source_row_number,
                        field_name="currency",
                        raw_value=r.currency,
                        reason_code="unsupported_currency",
                        severity="error",
                    )
                )
        return review_items


kosovo_rules_instance = KosovoMarketRules()
register_market_rules(kosovo_rules_instance)

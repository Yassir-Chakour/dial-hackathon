"""Italy market capability rules implementation."""

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
from app.ingestion.normalizers import parse_decimal

ITALY_RULES_VERSION = "italy-rules-v1.0"

COL_IT_COMPANY = 0
COL_IT_ORDER_NO = 1
COL_IT_SUB = 2
COL_IT_ORDER_TYPE_1 = 3
COL_IT_ORDER_TYPE_2 = 4
COL_IT_POSITION = 5
COL_IT_PE = 6
COL_IT_CODE = 7
COL_IT_DESCRIPTION = 8
COL_IT_GROSS_POS = 9
COL_IT_NET_POS = 10
COL_IT_PA = 11
COL_IT_PV = 12
COL_IT_QTY = 13
COL_IT_OP = 14
COL_IT_CATEGORY = 15

ITALY_PRODUCT_SUPPLIER_MAP: dict[str, tuple[str, str]] = {
    "WLF-1001": ("sup-arcus", "SATA"),
    "WLF-1002": ("sup-arcus", "SATA"),
    "WLF-1003": ("sup-arcus", "SATA"),
}


class ItalyMarketRules:
    """Market rules implementation for Italy (IT)."""

    market_code = "IT"
    rules_version = ITALY_RULES_VERSION
    supported_currencies = ("EUR",)

    def inspect_structure(
        self, rows: list[SourceRow], header_context: HeaderContext | None = None
    ) -> dict[str, Any]:
        sheets = {r.sheet_name for r in rows if r.sheet_name}
        return {
            "market_code": self.market_code,
            "layout": "italy_orders_multi_sheet",
            "sheets": sorted(sheets),
            "total_rows": len(rows),
        }

    def detect_scope(self, rows: list[SourceRow]) -> ScopeResult:
        suppliers_found: set[str] = set()
        evidence: list[dict[str, Any]] = []

        for r in rows:
            if len(r.cells) > COL_IT_CODE:
                code = str(r.cells[COL_IT_CODE]).strip()
                if code in ITALY_PRODUCT_SUPPLIER_MAP:
                    sup_id, _ = ITALY_PRODUCT_SUPPLIER_MAP[code]
                    suppliers_found.add(sup_id)
                    if len(evidence) < 3:
                        evidence.append({
                            "source_row": r.row_number,
                            "field": "Code",
                            "value": code,
                            "mapped_supplier": sup_id,
                        })

        supplier_list = sorted(suppliers_found) if suppliers_found else ["sup-arcus"]
        return ScopeResult(
            market="IT",
            update_mode="replacement",
            supplier_scope=supplier_list,
            confidence="high",
            evidence=evidence,
            reasons=["Italy v2 multi-sheet orders replacement detected."],
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

        raw_company = get_cell(COL_IT_COMPANY)
        raw_order = get_cell(COL_IT_ORDER_NO)
        raw_code = get_cell(COL_IT_CODE)
        raw_desc = get_cell(COL_IT_DESCRIPTION)
        raw_gross = get_cell(COL_IT_GROSS_POS)
        raw_net = get_cell(COL_IT_NET_POS)
        raw_pa = get_cell(COL_IT_PA)
        raw_qty = get_cell(COL_IT_QTY)
        raw_op = get_cell(COL_IT_OP)

        raw_values: dict[str, Any] = {
            "Company": raw_company,
            "Order no.": raw_order,
            "Code": raw_code,
            "Description": raw_desc,
            "Gross position": raw_gross,
            "Net position": raw_net,
            "PA": raw_pa,
            "Quantity": raw_qty,
            "Internal operation abbreviation": raw_op,
        }

        code_str = str(raw_code).strip() if raw_code is not None else ""
        supplier_id: str | None = None
        supplier_label: str | None = None
        if code_str in ITALY_PRODUCT_SUPPLIER_MAP:
            supplier_id, supplier_label = ITALY_PRODUCT_SUPPLIER_MAP[code_str]
        elif code_str:
            warnings.append(f"Product code {code_str} not mapped in Italy supplier map.")

        quantity = parse_decimal(raw_qty)
        if raw_qty is not None and quantity is None:
            errors.append(f"Could not parse quantity: {raw_qty}")

        signed_value = parse_decimal(raw_net)
        if raw_net is not None and signed_value is None:
            errors.append(f"Could not parse net position: {raw_net}")

        unit_price = parse_decimal(raw_pa)
        if unit_price is None and quantity and signed_value and quantity != Decimal("0"):
            unit_price = abs(signed_value / quantity)

        calculation_role: str = "included_in_line_sum"
        if record_kind in ("invoice_total", "header"):
            calculation_role = "excluded_from_line_sum"

        for field_name, raw_val_item in [
            ("Code", raw_code),
            ("Quantity", raw_qty),
            ("Net position", raw_net),
            ("Order no.", raw_order),
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
            supplier_id=supplier_id,
            supplier_label=supplier_label,
            product_id=code_str if code_str else None,
            product_label=str(raw_desc).strip() if raw_desc is not None else None,
            document_id=str(raw_order).strip() if raw_order is not None else None,
            transaction_date=None,
            quantity=quantity,
            unit="piece",
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
                        item_type="unsupported_currency",
                        source_record_key=r.source_record_key,
                        message=f"Currency '{r.currency}' not supported for Italy.",
                        severity="error",
                    )
                )
        return review_items


italy_rules_instance = ItalyMarketRules()
register_market_rules(italy_rules_instance)

"""Hungary market capability rules implementation."""

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
from app.ingestion.normalizers import normalize_unit, parse_decimal

HUNGARY_RULES_VERSION = "hungary-rules-v1.0"

COL_HU_BRAND = 0
COL_HU_SUPPLIER_CODE = 1
COL_HU_MFR_CODE = 2
COL_HU_DESCRIPTION = 3
COL_HU_UNIT = 4
COL_HU_QUANTITY = 5
COL_HU_PRICE_FT = 6

# Standard fixed FX rate from dataset fx-rates.json
HU_EUR_RATE = Decimal("394")

HUNGARY_BRAND_SUPPLIER_MAP: dict[str, tuple[str, str]] = {
    "WÜRTH": ("sup-orbit", "Würth"),
    "WUERTH": ("sup-orbit", "Würth"),
}


class HungaryMarketRules:
    """Market rules implementation for Hungary (HU)."""

    market_code = "HU"
    rules_version = HUNGARY_RULES_VERSION
    supported_currencies: tuple[str, ...] = ("HUF", "EUR")

    def inspect_structure(
        self, rows: list[SourceRow], header_context: HeaderContext | None = None
    ) -> dict[str, Any]:
        return {
            "market_code": self.market_code,
            "layout": "hungary_price_list_huf",
            "total_rows": len(rows),
        }

    def detect_scope(self, rows: list[SourceRow]) -> ScopeResult:
        suppliers_found: set[str] = set()
        evidence: list[dict[str, Any]] = []

        for r in rows:
            if len(r.cells) > COL_HU_BRAND:
                brand = str(r.cells[COL_HU_BRAND]).strip().upper()
                if brand in HUNGARY_BRAND_SUPPLIER_MAP:
                    sup_id, _ = HUNGARY_BRAND_SUPPLIER_MAP[brand]
                    suppliers_found.add(sup_id)
                    if len(evidence) < 3:
                        evidence.append({
                            "source_row": r.row_number,
                            "field": "Brand",
                            "value": brand,
                            "mapped_supplier": sup_id,
                        })

        supplier_list = sorted(suppliers_found) if suppliers_found else ["sup-orbit"]
        return ScopeResult(
            market="HU",
            update_mode="replacement",
            supplier_scope=supplier_list,
            confidence="high",
            evidence=evidence,
            reasons=["Hungary v2 distributor price replacement detected."],
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

        raw_brand = get_cell(COL_HU_BRAND)
        raw_sup_code = get_cell(COL_HU_SUPPLIER_CODE)
        raw_mfr_code = get_cell(COL_HU_MFR_CODE)
        raw_desc = get_cell(COL_HU_DESCRIPTION)
        raw_unit = get_cell(COL_HU_UNIT)
        raw_qty = get_cell(COL_HU_QUANTITY)
        raw_price_ft = get_cell(COL_HU_PRICE_FT)

        raw_values: dict[str, Any] = {
            "Brand": raw_brand,
            "Supplier Code": raw_sup_code,
            "Manufacturer Code": raw_mfr_code,
            "Item description": raw_desc,
            "Unit": raw_unit,
            "Quantity": raw_qty,
            "Selling Price/Unit (Ft)": raw_price_ft,
        }

        brand_str = str(raw_brand).strip().upper() if raw_brand is not None else ""
        supplier_id, supplier_label = HUNGARY_BRAND_SUPPLIER_MAP.get(
            brand_str, ("sup-orbit", "Würth")
        )

        mfr_code_str = str(raw_mfr_code).strip() if raw_mfr_code is not None else ""
        quantity = parse_decimal(raw_qty)
        if raw_qty is not None and quantity is None:
            errors.append(f"Could not parse quantity: {raw_qty}")

        unit_price_huf = parse_decimal(raw_price_ft)
        if raw_price_ft is not None and unit_price_huf is None:
            errors.append(f"Could not parse price Ft: {raw_price_ft}")

        # Total value in HUF
        signed_value_huf = None
        if quantity is not None and unit_price_huf is not None:
            signed_value_huf = quantity * unit_price_huf

        unit, unit_warn = normalize_unit(raw_unit)
        if unit_warn:
            warnings.append(unit_warn)

        calculation_role: str = "included_in_line_sum"
        if record_kind in ("invoice_total", "header"):
            calculation_role = "excluded_from_line_sum"

        for field_name, raw_val_item in [
            ("Manufacturer Code", raw_mfr_code),
            ("Quantity", raw_qty),
            ("Selling Price/Unit (Ft)", raw_price_ft),
            ("Supplier Code", raw_sup_code),
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
            product_id=mfr_code_str if mfr_code_str else None,
            product_label=str(raw_desc).strip() if raw_desc is not None else None,
            document_id=str(raw_sup_code).strip() if raw_sup_code is not None else None,
            transaction_date=None,
            quantity=quantity,
            unit=unit,
            currency="HUF",
            unit_price=unit_price_huf,
            signed_value=signed_value_huf,
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


hungary_rules_instance = HungaryMarketRules()
register_market_rules(hungary_rules_instance)

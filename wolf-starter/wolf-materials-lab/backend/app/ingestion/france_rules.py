"""France-specific layout mapping, alias tables, and replacement-scope detection."""

from decimal import Decimal
from typing import Any

from app.ingestion.contracts import (
    CanonicalSourceRecord,
    EvidenceRef,
    HeaderContext,
    RecordKind,
    ScopeResult,
    SourceRow,
)
from app.ingestion.normalizers import (
    normalize_currency,
    normalize_unit,
    parse_date,
    parse_decimal,
)

FRANCE_RULES_VERSION = "france-rules-v1.0"

# France layout column indices
COL_SITE_CODE = 0
COL_SITE_NAME = 1
COL_INVOICE_DATE = 2
COL_INVOICE_TOTAL = 3
COL_CURRENCY_1 = 4
COL_INVOICE_NUM_1 = 5
COL_ARTICLE = 6
COL_DESCRIPTION = 7
COL_QUANTITY = 8
COL_UNIT = 9
COL_NET_VALUE = 10
COL_CURRENCY_2 = 11
COL_ITEM_1 = 12
COL_INVOICE_NUM_2 = 13
COL_ITEM_2 = 14
COL_PRODUCT_GROUP = 15
COL_SALES_DOC = 18
COL_DOC_DATE = 19
COL_INVOICE_TYPE_CODE = 20
COL_ORDERING_PARTY = 21
COL_PAYER_1 = 22
COL_COMMERCIAL_DOC_TYPE = 26
COL_INVOICE_TYPE = 28
COL_PO_NUMBER = 31
COL_ORDER_DATE = 32
COL_PAYER_2 = 33

# Product to supplier alias mapping for the France replacement fixture
FRANCE_PRODUCT_SUPPLIER_MAP: dict[str, tuple[str, str]] = {
    "WLF-1008": ("sup-aster", "3M"),
    "WLF-1018": ("sup-aster", "3M"),
}


def is_france_layout(context: HeaderContext) -> bool:
    """Detect whether a header context corresponds to the France v2 34-column layout."""
    if len(context.raw_labels) < 20:
        return False
    norm = context.normalized_labels
    return "site code" in norm and "invoice date" in norm and "article" in norm and "net value" in norm


def extract_france_scope(rows: list[SourceRow]) -> ScopeResult:
    """Extract update scope from France records."""
    suppliers_found: set[str] = set()
    evidence: list[dict[str, Any]] = []

    for r in rows:
        if len(r.cells) > COL_ARTICLE:
            article = str(r.cells[COL_ARTICLE]).strip()
            if article in FRANCE_PRODUCT_SUPPLIER_MAP:
                sup_id, _ = FRANCE_PRODUCT_SUPPLIER_MAP[article]
                suppliers_found.add(sup_id)
                if len(evidence) < 3:
                    evidence.append({
                        "source_row": r.row_number,
                        "field": "article",
                        "value": article,
                        "mapped_supplier": sup_id,
                    })

    supplier_list = sorted(suppliers_found) if suppliers_found else ["sup-aster"]
    return ScopeResult(
        market="FR",
        update_mode="replacement",
        supplier_scope=supplier_list,
        confidence="high",
        evidence=evidence,
        reasons=["France v2 supplier subset replacement detected based on article codes."],
    )


def map_france_row(
    row: SourceRow,
    record_kind: RecordKind,
    source_record_key: str,
) -> CanonicalSourceRecord:
    """Map a France fixture row into a CanonicalSourceRecord according to positional rules."""
    cells = row.cells
    warnings: list[str] = []
    errors: list[str] = []
    evidence_list: list[EvidenceRef] = []

    def get_cell(idx: int) -> Any:
        return cells[idx] if idx < len(cells) else None

    raw_article = get_cell(COL_ARTICLE)
    raw_desc = get_cell(COL_DESCRIPTION)
    raw_invoice = get_cell(COL_INVOICE_NUM_1)
    raw_date = get_cell(COL_INVOICE_DATE)
    raw_qty = get_cell(COL_QUANTITY)
    raw_unit = get_cell(COL_UNIT)
    raw_val = get_cell(COL_NET_VALUE)
    raw_curr = get_cell(COL_CURRENCY_1)
    raw_item = get_cell(COL_ITEM_1)
    raw_doc_type = get_cell(COL_INVOICE_TYPE_CODE)

    # Attach raw values dict
    raw_values: dict[str, Any] = {
        "Site code": get_cell(COL_SITE_CODE),
        "SITE": get_cell(COL_SITE_NAME),
        "Invoice date": raw_date,
        "Invoice total": get_cell(COL_INVOICE_TOTAL),
        "Invoice": raw_invoice,
        "Article": raw_article,
        "Description": raw_desc,
        "Invoiced quantity": raw_qty,
        "Quantity unit": raw_unit,
        "Net value": raw_val,
        "Currency": raw_curr,
        "Item": raw_item,
        "Invoice type code": raw_doc_type,
    }

    # Supplier mapping from article
    article_str = str(raw_article).strip() if raw_article is not None else None
    supplier_id: str | None = None
    supplier_label: str | None = None
    if article_str and article_str in FRANCE_PRODUCT_SUPPLIER_MAP:
        supplier_id, supplier_label = FRANCE_PRODUCT_SUPPLIER_MAP[article_str]
    elif article_str:
        warnings.append(f"Article {article_str} not found in France product supplier map.")

    product_id = article_str
    product_label = str(raw_desc).strip() if raw_desc is not None else None
    document_id = str(raw_invoice).strip() if raw_invoice is not None else None

    # Date parsing
    tx_date = parse_date(raw_date)
    if raw_date is not None and tx_date is None:
        errors.append(f"Could not parse invoice date: {raw_date}")

    # Quantity parsing
    quantity = parse_decimal(raw_qty)
    if raw_qty is not None and quantity is None:
        errors.append(f"Could not parse quantity: {raw_qty}")

    # Unit normalization
    unit, unit_warn = normalize_unit(raw_unit)
    if unit_warn:
        warnings.append(unit_warn)

    # Net value parsing
    signed_value = parse_decimal(raw_val)
    if raw_val is not None and signed_value is None:
        errors.append(f"Could not parse net value: {raw_val}")

    # Currency normalization
    currency = normalize_currency(raw_curr)

    # Unit price calculation
    unit_price: Decimal | None = None
    if quantity is not None and signed_value is not None and quantity != Decimal("0"):
        unit_price = abs(signed_value / quantity)

    # Exclude invoice total from line sum calculation
    calculation_role: str = "included_in_line_sum"
    if record_kind in ("invoice_total", "header"):
        calculation_role = "excluded_from_line_sum"

    # Build field-level evidence
    for field_name, raw_val_item in [
        ("article", raw_article),
        ("quantity", raw_qty),
        ("net_value", raw_val),
        ("invoice", raw_invoice),
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
        product_id=product_id,
        product_label=product_label,
        document_id=document_id,
        transaction_date=tx_date,
        quantity=quantity,
        unit=unit,
        currency=currency,
        unit_price=unit_price,
        signed_value=signed_value,
        validation_status="valid" if not errors else "invalid",
        warnings=warnings,
        errors=errors,
        evidence=evidence_list,
        raw_values=raw_values,
    )

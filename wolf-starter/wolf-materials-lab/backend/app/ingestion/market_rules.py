"""Market capability protocol and registry for multi-market extensibility."""

from typing import Any, Protocol, runtime_checkable

from app.ingestion.contracts import (
    CanonicalSourceRecord,
    HeaderContext,
    RecordKind,
    ReviewItem,
    ScopeResult,
    SourceRow,
)


@runtime_checkable
class MarketRules(Protocol):
    """Capability interface for country-specific layout, mapping and validation rules."""

    market_code: str
    rules_version: str
    supported_currencies: tuple[str, ...]

    def inspect_structure(
        self, rows: list[SourceRow], header_context: HeaderContext | None = None
    ) -> dict[str, Any]:
        """Inspect structure, layout, and column presence for this market."""
        ...

    def detect_scope(self, rows: list[SourceRow]) -> ScopeResult:
        """Detect update scope (supplier subset, replacement, etc.) from extracted rows."""
        ...

    def normalize_record(
        self,
        row: SourceRow,
        record_kind: RecordKind,
        source_record_key: str,
    ) -> CanonicalSourceRecord:
        """Map a raw SourceRow into a CanonicalSourceRecord according to market rules."""
        ...

    def validate_update(self, records: list[CanonicalSourceRecord]) -> list[ReviewItem]:
        """Run market-specific semantic validations on normalized records."""
        ...


_MARKET_REGISTRY: dict[str, MarketRules] = {}


def register_market_rules(rules: MarketRules) -> None:
    """Register market capability rules by market code."""
    _MARKET_REGISTRY[rules.market_code.upper()] = rules


def get_market_rules(market_code: str) -> MarketRules:
    """Retrieve market rules for a specific ISO country code, failing closed if unsupported."""
    code = market_code.strip().upper()
    if code not in _MARKET_REGISTRY:
        raise ValueError(
            f"Unsupported market code '{market_code}'. Supported markets: {sorted(_MARKET_REGISTRY.keys())}"
        )
    return _MARKET_REGISTRY[code]


def list_supported_markets() -> list[dict[str, Any]]:
    """Return summary metadata for all registered markets."""
    return [
        {
            "market_code": rules.market_code,
            "rules_version": rules.rules_version,
            "supported_currencies": list(rules.supported_currencies),
        }
        for rules in sorted(_MARKET_REGISTRY.values(), key=lambda r: r.market_code)
    ]


def detect_market(
    rows: list[SourceRow], header_context: HeaderContext | None = None
) -> MarketRules | None:
    """Inspect rows and candidate header contexts to automatically detect market."""
    if not rows:
        return None

    # Check filename / sheet prefixes first if available
    first_row = rows[0]
    filename = (first_row.metadata.get("filename") or "").upper()
    sheet_name = (first_row.sheet_name or "").upper()

    if "FR" in filename or "FRANCE" in filename:
        return _MARKET_REGISTRY.get("FR")
    if "IT" in filename or "ITALY" in filename or "MA CARR" in sheet_name or "MA VERN" in sheet_name:
        return _MARKET_REGISTRY.get("IT")
    if "HU" in filename or "HUNGARY" in filename:
        return _MARKET_REGISTRY.get("HU")
    if "XK" in filename or "KOSOVO" in filename:
        return _MARKET_REGISTRY.get("XK")

    # Header-based heuristic
    if header_context:
        norm = set(header_context.normalized_labels)
        if "site code" in norm and "net value" in norm:
            return _MARKET_REGISTRY.get("FR")
        if "pa" in norm and "pv" in norm and "gross position" in norm:
            return _MARKET_REGISTRY.get("IT")
        if "selling price/unit (ft)" in norm or "manufacturer code" in norm:
            return _MARKET_REGISTRY.get("HU")
        if "total excl. vat" in norm or "vat" in norm:
            return _MARKET_REGISTRY.get("XK")

    # Content-based heuristic in first few rows
    for row in rows[:5]:
        line_str = " ".join(str(c) for c in row.cells).lower()
        if "kosovo" in line_str:
            return _MARKET_REGISTRY.get("XK")
        if "wolf atelier france" in line_str:
            return _MARKET_REGISTRY.get("FR")
        if "ma carr" in line_str or "ma vern" in line_str:
            return _MARKET_REGISTRY.get("IT")
        if "würth" in line_str or "wuerth" in line_str:
            return _MARKET_REGISTRY.get("HU")

    # Default to France if standard 34-column layout detected
    if header_context and len(header_context.raw_labels) >= 20:
        return _MARKET_REGISTRY.get("FR")

    return None

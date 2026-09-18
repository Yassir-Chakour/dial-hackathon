"""Tests for field normalization: decimals, Excel serial dates, currencies, and units."""

from datetime import date
from decimal import Decimal

from app.ingestion.normalizers import (
    normalize_currency,
    normalize_unit,
    parse_date,
    parse_decimal,
)


def test_parse_decimal_formats() -> None:
    """Test parsing integers, floats, negative values, and European commas."""
    assert parse_decimal("1234.56") == Decimal("1234.56")
    assert parse_decimal("1234,56") == Decimal("1234.56")
    assert parse_decimal("1.234,56") == Decimal("1234.56")
    assert parse_decimal("1,234.56") == Decimal("1234.56")
    assert parse_decimal("-11336.16") == Decimal("-11336.16")
    assert parse_decimal("-11336,16") == Decimal("-11336.16")
    assert parse_decimal(100) == Decimal("100")
    assert parse_decimal(None) is None
    assert parse_decimal("invalid") is None


def test_parse_date_excel_and_iso() -> None:
    """Test parsing Excel serial dates and standard date formats."""
    # 46270 corresponds to 2026-09-05
    assert parse_date(46270) == date(2026, 9, 5)
    assert parse_date("46270") == date(2026, 9, 5)

    assert parse_date("2026-01-10") == date(2026, 1, 10)
    assert parse_date("10/01/2026") == date(2026, 1, 10)

    # 2-digit ambiguous years rejected
    assert parse_date("01/02/03") is None
    assert parse_date(None) is None


def test_normalize_currency() -> None:
    """Test currency string normalization."""
    assert normalize_currency("EUR") == "EUR"
    assert normalize_currency("eur") == "EUR"
    assert normalize_currency("€") == "EUR"
    assert normalize_currency("$") == "USD"
    assert normalize_currency("huf") == "HUF"
    assert normalize_currency(None) is None


def test_normalize_unit() -> None:
    """Test quantity unit normalization and unknown unit preservation."""
    unit, warn = normalize_unit("PC")
    assert unit == "piece"
    assert warn is None

    unit2, warn2 = normalize_unit("pcs")
    assert unit2 == "piece"
    assert warn2 is None

    unit3, warn3 = normalize_unit("box_of_unknown")
    assert unit3 == "box_of_unknown"
    assert warn3 is not None
    assert "Unrecognized unit" in warn3

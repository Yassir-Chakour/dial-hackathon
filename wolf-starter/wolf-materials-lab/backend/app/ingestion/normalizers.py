"""Pure field normalization functions using Decimal and explicit locale rules."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any

EXCEL_BASE_DATE = date(1899, 12, 30)

UNIT_ALIASES: dict[str, str] = {
    "pc": "piece",
    "pcs": "piece",
    "piece": "piece",
    "pieces": "piece",
    "stk": "piece",
    "stück": "piece",
    "stueck": "piece",
    "ea": "piece",
    "set": "set",
    "pack": "pack",
    "l": "liter",
    "liter": "liter",
    "kg": "kg",
}


def parse_decimal(value: Any) -> Decimal | None:
    """Parse a numeric value or string into an exact Decimal.

    Supports negative values, European commas (e.g. '1234,56'), and standard dots.
    Returns None if value is empty or None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value

    s = str(value).strip()
    if not s:
        return None

    # Remove non-breaking spaces or currency symbols
    s = s.replace("\xa0", "").replace(" ", "").replace("€", "").replace("$", "")

    # Handle European comma vs dot:
    # If comma is present and no dot, or comma is after dot, treat comma as decimal sep
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # Format: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:
            # Format: 1,234.56
            s = s.replace(",", "")

    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_date(value: Any, formats: list[str] | None = None) -> date | None:
    """Parse date from string or Excel serial number.

    Supports Excel serial dates (e.g. 46270 -> 2026-09-04),
    ISO 'YYYY-MM-DD', and French/European 'DD/MM/YYYY' or 'DD.MM.YYYY'.
    Rejects 2-digit ambiguous years.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    # Check Excel serial number (integer or float)
    if isinstance(value, (int, float)):
        val_int = int(value)
        # Excel serial 40000..60000 spans 2009 to 2064
        if 20000 <= val_int <= 80000:
            return EXCEL_BASE_DATE + timedelta(days=val_int)

    s = str(value).strip()
    if not s:
        return None

    # Check numeric string for Excel serial
    if s.isdigit() and len(s) == 5:
        val_int = int(s)
        if 20000 <= val_int <= 80000:
            return EXCEL_BASE_DATE + timedelta(days=val_int)

    # Reject 2-digit year patterns like 01/02/03 as ambiguous
    if re.match(r"^\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2}$", s):
        return None

    allowed_formats = formats or [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]

    for fmt in allowed_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    return None


def normalize_currency(value: Any) -> str | None:
    """Normalize a currency code to uppercase 3-letter ISO string."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if len(s) == 3 and s.isalpha():
        return s
    if s in ("€", "EURO"):
        return "EUR"
    if s in ("$", "USD"):
        return "USD"
    return s if s else None


def normalize_unit(
    value: Any, aliases: dict[str, str] | None = None
) -> tuple[str | None, str | None]:
    """Normalize a quantity unit using standard and supplied aliases.

    Returns (normalized_unit, warning_message).
    """
    if value is None:
        return None, "Unit is missing"
    s = str(value).strip().lower()
    if not s:
        return None, "Unit is empty"

    unit_map = {**UNIT_ALIASES, **(aliases or {})}
    if s in unit_map:
        return unit_map[s], None

    return s, f"Unrecognized unit '{s}' preserved without conversion factor"


def normalize_identifier(value: Any, aliases: dict[str, str] | None = None) -> str | None:
    """Normalize a supplier or product identifier through alias lookup."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if aliases and s in aliases:
        return aliases[s]
    return s

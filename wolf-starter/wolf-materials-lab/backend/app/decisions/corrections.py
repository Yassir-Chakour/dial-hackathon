"""Append-only reviewer correction validation."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any


def validate_correction(correction: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    required = ("field_name", "corrected_value", "reviewer_id", "reason")
    missing = [key for key in required if not correction.get(key)]
    if missing:
        raise ValueError(f"correction_missing_fields: {', '.join(missing)}")
    if len(str(correction["reason"])) > 1000:
        raise ValueError("correction_reason_too_long")
    field = str(correction["field_name"])
    if field not in target:
        raise ValueError("correction_field_not_supported")
    if field in {"market", "source_version_id", "supplier_owner"}:
        raise ValueError("correction_requires_reconciliation")
    if field in {"quantity", "value", "baseline_value"}:
        try:
            Decimal(str(correction["corrected_value"]))
        except InvalidOperation as exc:
            raise ValueError("correction_value_invalid") from exc
    if field in {"currency", "unit"} and not str(correction["corrected_value"]).strip():
        raise ValueError("correction_semantics_invalid")
    result = {"field_name": field, "original_value": target.get(field), "corrected_value": correction["corrected_value"],
              "reviewer_id": str(correction["reviewer_id"]), "reason": str(correction["reason"]),
              "requires_reconciliation": field in {"currency", "unit"}}
    result["correction_hash"] = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
    return result

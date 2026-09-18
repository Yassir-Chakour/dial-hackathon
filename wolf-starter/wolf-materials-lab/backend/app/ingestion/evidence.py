"""Evidence linking and deterministic result hashing."""

import hashlib
import json
from typing import Any

from app.ingestion.contracts import EvidenceRef


def build_evidence_ref(
    source_file_id: str,
    source_version_id: str,
    source_row_number: int,
    sheet_name: str | None = None,
    field_name: str | None = None,
    raw_value: Any = None,
) -> EvidenceRef:
    """Construct an EvidenceRef link."""
    return EvidenceRef(
        source_file_id=source_file_id,
        source_version_id=source_version_id,
        source_row_number=source_row_number,
        sheet_name=sheet_name,
        field_name=field_name,
        raw_value=str(raw_value) if raw_value is not None else None,
    )


def compute_ingestion_result_hash(payload: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash over canonical results.

    Excludes timestamps and random IDs to ensure replay determinism.
    """
    # Canonical JSON serialization with sorted keys
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(serialized).hexdigest()

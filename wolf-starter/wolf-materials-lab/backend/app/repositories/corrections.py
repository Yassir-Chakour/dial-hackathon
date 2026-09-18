"""Append-only correction repository."""

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Correction
from app.decisions.corrections import validate_correction


class CorrectionRepository:
    def submit(self, session: Session, *, source_record_id: str, target: dict[str, Any], correction: dict[str, Any]) -> Correction:
        checked = validate_correction(correction, target)
        row = Correction(source_record_id=source_record_id, field_name=checked["field_name"],
                         original_value=str(checked["original_value"]) if checked["original_value"] is not None else None,
                         corrected_value=str(checked["corrected_value"]), reviewer_id=checked["reviewer_id"],
                         reason=checked["reason"], correction_hash=checked["correction_hash"],
                         validation_type="schema_and_domain", requires_reconciliation=checked["requires_reconciliation"])
        session.add(row)
        session.flush()
        return row

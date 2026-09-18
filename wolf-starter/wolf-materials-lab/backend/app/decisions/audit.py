"""Safe append-only audit event construction."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.schemas.common import utc_now


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor_id: str | None
    target_id: str
    previous_status: str | None = None
    current_status: str | None = None
    input_hash: str | None = None
    result_hash: str | None = None
    policy_version: str | None = None
    reason_codes: tuple[str, ...] = ()
    request_id: str | None = None
    event_id: str = ""
    created_at: datetime = utc_now()


def record_audit_event(event_type: str, target_id: str, *, actor_id: str | None = None,
                       previous_status: str | None = None, current_status: str | None = None,
                       input_hash: str | None = None, result_hash: str | None = None,
                       policy_version: str | None = None, reason_codes: tuple[str, ...] = (),
                       request_id: str | None = None) -> AuditEvent:
    return AuditEvent(event_type, actor_id, target_id, previous_status, current_status, input_hash,
                      result_hash, policy_version, reason_codes, request_id, str(uuid4()), utc_now())

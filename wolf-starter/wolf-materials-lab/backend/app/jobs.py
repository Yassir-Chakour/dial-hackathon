"""Durable job contracts and retry classification for worker services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class FailureClass(StrEnum):
    TRANSIENT = "transient"
    DATA = "data"
    AUTHORIZATION = "authorization"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    next_status: JobStatus
    reason_code: str


def classify_failure(*, failure_class: FailureClass, attempts: int, max_attempts: int) -> RetryDecision:
    """Classify a failure without retrying unsafe data or authorization errors."""
    if attempts < 0 or max_attempts < 1:
        raise ValueError("attempts must be non-negative and max_attempts must be positive")
    if failure_class == FailureClass.TRANSIENT and attempts < max_attempts:
        return RetryDecision(True, JobStatus.RETRYING, "transient_failure")
    if failure_class == FailureClass.TRANSIENT:
        return RetryDecision(False, JobStatus.DEAD_LETTER, "retry_limit_exceeded")
    if failure_class == FailureClass.AUTHORIZATION:
        return RetryDecision(False, JobStatus.FAILED, "authorization_failed")
    if failure_class == FailureClass.DATA:
        return RetryDecision(False, JobStatus.FAILED, "invalid_input")
    if failure_class == FailureClass.CONFLICT:
        return RetryDecision(False, JobStatus.FAILED, "state_conflict")
    return RetryDecision(False, JobStatus.DEAD_LETTER, "unknown_failure")


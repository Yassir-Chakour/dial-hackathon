"""Transactional repository for durable background jobs."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JobRecord
from app.jobs import FailureClass, JobStatus, classify_failure


class JobRepository:
    def create_or_get(
        self,
        session: Session,
        *,
        job_type: str,
        idempotency_key: str,
        input_fingerprint: str,
        payload: dict[str, Any],
        tenant_id: str | None = None,
        max_attempts: int = 3,
    ) -> tuple[JobRecord, bool]:
        existing = session.scalar(select(JobRecord).where(
            JobRecord.tenant_id == tenant_id,
            JobRecord.idempotency_key == idempotency_key,
        ))
        if existing:
            if existing.input_fingerprint != input_fingerprint:
                raise ValueError("Job idempotency key conflicts with a different input fingerprint.")
            return existing, True
        job = JobRecord(
            tenant_id=tenant_id,
            job_type=job_type,
            idempotency_key=idempotency_key,
            input_fingerprint=input_fingerprint,
            payload_json=payload,
            max_attempts=max_attempts,
        )
        session.add(job)
        session.flush()
        return job, False

    def start(self, session: Session, job_id: str) -> JobRecord:
        job = session.get(JobRecord, job_id)
        if job is None or job.status not in {JobStatus.QUEUED.value, JobStatus.RETRYING.value}:
            raise ValueError("Job is missing or not available to start.")
        job.status = JobStatus.RUNNING.value
        job.attempt_count += 1
        return job

    def fail(
        self,
        session: Session,
        job_id: str,
        *,
        failure_class: FailureClass,
        error_code: str,
        error_summary: str,
    ) -> JobRecord:
        job = session.get(JobRecord, job_id)
        if job is None:
            raise ValueError("Job does not exist.")
        decision = classify_failure(
            failure_class=failure_class,
            attempts=job.attempt_count,
            max_attempts=job.max_attempts,
        )
        job.status = decision.next_status.value
        job.last_error_code = error_code[:64]
        job.last_error_summary = error_summary[:512]
        if decision.retry:
            job.available_at = datetime.now(timezone.utc)
        return job

    def succeed(self, session: Session, job_id: str) -> JobRecord:
        job = session.get(JobRecord, job_id)
        if job is None or job.status != JobStatus.RUNNING.value:
            raise ValueError("Job is missing or not running.")
        job.status = JobStatus.SUCCEEDED.value
        return job

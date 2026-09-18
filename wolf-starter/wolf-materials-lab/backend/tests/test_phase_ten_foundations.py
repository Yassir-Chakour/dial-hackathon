"""Local verification of Phase Ten storage and worker safety contracts."""

import pytest

from app.jobs import FailureClass, JobStatus, classify_failure
from app.db.models import JobRecord
from app.repositories.jobs import JobRepository
from app.storage import PrivateObjectStore, RetentionError, StorageError


def test_private_object_store_uses_opaque_keys_and_round_trips(tmp_path) -> None:
    store = PrivateObjectStore(tmp_path)
    stored = store.put(b"private source", media_type="text/csv")
    assert stored.object_key.startswith("objects/")
    assert "source" not in stored.object_key
    assert store.get(stored.object_key) == b"private source"


def test_private_object_store_rejects_path_escape_and_retained_delete(tmp_path) -> None:
    store = PrivateObjectStore(tmp_path)
    with pytest.raises(StorageError):
        store.get("../../etc/passwd")
    stored = store.put(b"protected", media_type="application/octet-stream")
    with pytest.raises(RetentionError):
        store.delete(stored.object_key, retention_status="legal_hold")
    assert store.get(stored.object_key) == b"protected"


def test_worker_retries_only_transient_failures() -> None:
    retry = classify_failure(failure_class=FailureClass.TRANSIENT, attempts=1, max_attempts=3)
    assert retry.retry is True
    assert retry.next_status == JobStatus.RETRYING

    dead = classify_failure(failure_class=FailureClass.TRANSIENT, attempts=3, max_attempts=3)
    assert dead.next_status == JobStatus.DEAD_LETTER

    auth = classify_failure(failure_class=FailureClass.AUTHORIZATION, attempts=0, max_attempts=3)
    assert auth.retry is False
    assert auth.next_status == JobStatus.FAILED


def test_job_repository_is_idempotent_and_dead_letters_data_errors(app) -> None:
    repository = JobRepository()
    with app.state.test_db.transaction() as session:
        job, replayed = repository.create_or_get(
            session,
            tenant_id="tenant-a",
            job_type="source_ingestion",
            idempotency_key="job-1",
            input_fingerprint="a" * 64,
            payload={"source_file_id": "source-1"},
        )
        assert replayed is False
        same_job, replayed = repository.create_or_get(
            session,
            tenant_id="tenant-a",
            job_type="source_ingestion",
            idempotency_key="job-1",
            input_fingerprint="a" * 64,
            payload={"source_file_id": "source-1"},
        )
        assert same_job.id == job.id
        assert replayed is True
        repository.start(session, job.id)
        failed = repository.fail(
            session,
            job.id,
            failure_class=FailureClass.DATA,
            error_code="invalid_source",
            error_summary="Malformed workbook",
        )
        assert failed.status == JobStatus.FAILED.value
        assert session.get(JobRecord, job.id).last_error_code == "invalid_source"

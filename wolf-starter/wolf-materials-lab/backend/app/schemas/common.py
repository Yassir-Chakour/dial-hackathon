"""Common Pydantic schemas and utility functions."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class ErrorDetail(BaseModel):
    """Detailed error location and description."""

    model_config = ConfigDict(extra="forbid")

    loc: list[str | int] | None = None
    msg: str
    type: str | None = None


class ErrorResponse(BaseModel):
    """Standard unified error envelope for all API errors."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ServiceStatus(BaseModel):
    """Service status response for liveness and readiness probes."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "ready", "not_ready"]
    service: str
    version: str
    checks: dict[str, Literal["ok", "failed"]] | None = None


class EvidenceReference(BaseModel):
    """Future contract: link a result to a verified source row."""

    model_config = ConfigDict(extra="forbid")

    file_hash: str = Field(..., max_length=128)
    source_name: str = Field(..., max_length=256)
    row_number: int = Field(..., ge=1)
    field_name: str | None = Field(default=None, max_length=128)


class SourceReference(BaseModel):
    """Future contract: track source file identifier and version lineage."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., max_length=64)
    version: str = Field(..., max_length=32)
    file_hash: str = Field(..., max_length=128)

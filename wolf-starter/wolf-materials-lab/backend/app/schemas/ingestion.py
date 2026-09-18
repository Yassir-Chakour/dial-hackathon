"""Public API schemas for ingestion endpoints."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestMatrixRequest(BaseModel):
    """Request payload for raw matrix ingestion."""

    model_config = ConfigDict(extra="forbid")

    matrix: list[list[Any]]
    filename: str = Field(default="FR-v2.json", max_length=256)
    event_key: str | None = Field(default=None, max_length=256)
    tenant_id: str | None = Field(default=None, max_length=128)


class IngestionResponse(BaseModel):
    """Response returned upon successful ingestion of a supplier source."""

    model_config = ConfigDict(extra="forbid")

    source_file_id: str
    source_version_id: str
    status: str
    market: str
    update_mode: str
    supplier_scope: list[str]
    total_rows: int
    record_count: int
    valid_count: int
    review_count: int
    result_hash: str
    replayed: bool = False

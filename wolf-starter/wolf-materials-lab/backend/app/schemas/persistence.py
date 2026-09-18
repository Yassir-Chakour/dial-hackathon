"""Pydantic boundaries for persistence inputs and safe outputs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceFileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_filename: str = Field(min_length=1, max_length=256)
    media_type: str = Field(min_length=1, max_length=128)
    content: bytes
    source_system: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_key: str = Field(min_length=1, max_length=256)
    source_row_number: int = Field(ge=1)
    source_sheet: str | None = Field(default=None, max_length=256)
    raw_values: dict[str, Any]
    record_kind: str = Field(default="unknown", max_length=32)
    validation_status: Literal["valid", "ambiguous", "invalid"] = "valid"
    validation_errors: list[str] = Field(default_factory=list)


class SourceVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    market: str
    version_label: str
    scope_key: str
    status: str
    created_at: datetime
    accepted_at: datetime | None = None


class RecommendationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_version_id: str
    recommendation_key: str
    status: str
    calculation_hash: str
    created_at: datetime

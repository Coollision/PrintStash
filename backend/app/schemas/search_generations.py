"""Immutable generation proposals and administrative work status."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GenerationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    endpoint_id: int = Field(ge=1)
    profile: Literal["semantic_text"] = "semantic_text"
    query_prefix: str | None = Field(default=None, max_length=256)
    document_prefix: str | None = Field(default=None, max_length=256)
    passage_recipe_version: int = Field(default=1, ge=1)
    index_backend: Literal["auto", "numpy", "sqlite_vec", "pgvector"] = "auto"
    index_dimension: int | None = Field(default=None, ge=1, le=4096)
    quantization: Literal["float32", "int8", "binary"] = "float32"
    auto_activate: bool = True


class GenerationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_token: str = Field(pattern=r"^[0-9a-f]{32}$")


class GenerationRead(BaseModel):
    id: int
    state: str
    phase: str
    version_token: str | None
    modality: str
    profile: str
    model: str
    config_hash: str
    native_dimension: int
    index_dimension: int
    quantization: str
    index_backend: str
    effective_backend: str
    index_state: str
    index_error: str | None
    error_code: str | None
    processed: int
    copied: int
    truncated_count: int
    eligible: int
    indexed: int
    quarantined: int
    estimated_bytes: int
    job_id: str | None
    verified_at: datetime | None
    retain_until: datetime | None

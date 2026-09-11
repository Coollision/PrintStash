"""Admin disclosures contain model metadata, never server filesystem paths."""

from pydantic import BaseModel


class InferenceModelRead(BaseModel):
    id: str
    key: str
    revision: str
    repository: str | None
    languages: list[str]
    license: str | None
    modality: str
    native_dimension: int
    size_bytes: int
    installed: bool
    curated: bool
    referenced: bool
    runtime_available: bool


class DownloadRead(BaseModel):
    job_id: str


class ModelValidationRead(BaseModel):
    id: str
    ready: bool

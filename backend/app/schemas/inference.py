"""Admin-only immutable endpoint proposals and secret-free disclosures."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.inference.endpoint import EndpointParameters


class EndpointProposal(EndpointParameters):
    kind: Literal["embedding", "chat"] = "embedding"
    native_dimension: int | None = Field(default=None, ge=1, le=4096)
    supports_images: bool = False

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind == "embedding" and (
            self.native_dimension is None
            or self.supports_images
            or self.prefer_responses
        ):
            raise ValueError("embedding_text_dimension_required")
        if self.kind == "chat" and self.native_dimension is not None:
            raise ValueError("chat_dimension_forbidden")
        return self


class EndpointRead(BaseModel):
    id: int
    kind: str
    host: str
    model: str
    revision: str
    config_hash: str
    native_dimension: int | None
    supports_images: bool
    dialect: str | None
    guarantee: str | None
    has_credentials: bool


class SearchSettings(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    enabled: bool = False
    captions_enabled: bool = False
    nl_filters_enabled: bool = False
    local_models_enabled: bool = False
    send_rendered_images: bool = False
    send_query_images: bool = False
    chat_endpoint_id: int | None = Field(default=None, ge=1)
    rollback_retention_hours: int = Field(default=24, ge=1, le=720)
    max_index_bytes: int = Field(default=2147483648, ge=1048576, le=1099511627776)


class SearchSettingsRead(BaseModel):
    settings: SearchSettings
    endpoints: list[EndpointRead]

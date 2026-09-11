"""Durable text projections; inference and native indexes are separate derivatives."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow

from .base import SQLModel


class SearchPassage(SQLModel, table=True):
    __tablename__ = "search_passages"
    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "visibility_segment_key",
            "chunk_index",
            "recipe_version",
            name="uq_search_passage_identity",
        ),
        CheckConstraint(
            "subject_type IN ('model', 'collection', 'multipart_model', 'document')",
            name="subject_type",
        ),
        CheckConstraint("subject_id > 0", name="subject_id"),
        CheckConstraint("chunk_index >= 0 AND chunk_index < 16", name="chunk_index"),
        CheckConstraint("recipe_version > 0", name="recipe_version"),
        CheckConstraint("length(text) <= 16384", name="text_length"),
        Index("ix_search_passages_watermark", "updated_at", "id"),
    )
    id: int | None = Field(default=None, primary_key=True)
    subject_type: str = Field(max_length=32)
    subject_id: int
    visibility_segment_key: str = Field(max_length=64)
    # Additional Subject permissions, conjunctive; owner permission is mandatory.
    access_dependencies_json: str = Field(sa_column=Column(Text, nullable=False))
    chunk_index: int
    recipe_version: int
    content_hash: str = Field(max_length=64)
    text: str = Field(sa_column=Column(Text, nullable=False))
    truncated: bool = False
    source_updated_at: datetime
    updated_at: datetime = Field(default_factory=utcnow)

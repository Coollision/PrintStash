"""Durable passage fixtures use the same immutable recipe identity as search."""

from typing import Any

from printstash_core.search.passages import (
    RECIPE_VERSION,
    PassageContent,
    SearchSubject,
    access_identity,
    render_passages,
)
from sqlmodel import Session

from app.core.time import utcnow
from app.db.models.search import SearchPassage
from tests.factories._support import save


def build_search_passage(
    session: Session, subject: SearchSubject, **overrides: Any
) -> SearchPassage:
    passage = render_passages(PassageContent(title="Stored passage"))[0]
    segment_key, dependencies = access_identity(())
    defaults = {
        "subject_type": subject.subject_type.value,
        "subject_id": subject.subject_id,
        "visibility_segment_key": segment_key,
        "access_dependencies_json": dependencies,
        "chunk_index": 0,
        "recipe_version": RECIPE_VERSION,
        "content_hash": passage.content_hash,
        "text": passage.text,
        "source_updated_at": utcnow(),
    }
    return save(session, SearchPassage(**(defaults | overrides)))

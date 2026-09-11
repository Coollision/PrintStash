"""Transactional passage replacement without inference or an implicit commit.

This internal operation is intentionally not wired into library writes yet.
W1's injected mutation port and reconciliation worker will call it in the
content transaction; W2 will attach a synchronous derived lexical projection.
"""

from __future__ import annotations

from dataclasses import dataclass

from printstash_core.search.passages import (
    RECIPE_VERSION,
    SearchSubject,
    access_identity,
    render_passages,
)
from sqlmodel import Session, select

from app.core.time import utcnow
from app.db.models.search import SearchPassage
from app.modules.search.sources import project_subject


@dataclass(frozen=True)
class PassageChanges:
    inserted: int = 0
    updated: int = 0
    removed: int = 0


def sync_subject(session: Session, subject: SearchSubject) -> PassageChanges:
    """Replace this recipe only; missing/trashed Subjects lose every recipe.

    The caller serializes writes to a Subject and owns commit/rollback. Stable
    passage IDs and hashes let later backfill workers distinguish an indexed
    content edit from unrelated bookkeeping without relying on timestamps.
    """
    projection = project_subject(session, subject)
    statement = select(SearchPassage).where(
        SearchPassage.subject_type == subject.subject_type.value,
        SearchPassage.subject_id == subject.subject_id,
    )
    if projection is not None:
        statement = statement.where(SearchPassage.recipe_version == RECIPE_VERSION)
    rows = session.exec(statement).all()
    if projection is None:
        for row in rows:
            session.delete(row)
        session.flush()
        return PassageChanges(removed=len(rows))
    existing = {(row.visibility_segment_key, row.chunk_index): row for row in rows}
    inserted = updated = 0
    for segment in projection.segments:
        segment_key, dependencies_json = access_identity(segment.access_dependencies)
        for passage in render_passages(segment.content):
            key = (segment_key, passage.chunk_index)
            row = existing.pop(key, None)
            values = {
                "access_dependencies_json": dependencies_json,
                "content_hash": passage.content_hash,
                "text": passage.text,
                "truncated": passage.truncated or segment.truncated,
            }
            if row is None:
                row = SearchPassage(
                    subject_type=subject.subject_type.value,
                    subject_id=subject.subject_id,
                    visibility_segment_key=segment_key,
                    chunk_index=passage.chunk_index,
                    recipe_version=RECIPE_VERSION,
                    source_updated_at=projection.source_updated_at,
                    **values,
                )
                inserted += 1
            elif any(getattr(row, field) != value for field, value in values.items()):
                for field, value in values.items():
                    setattr(row, field, value)
                row.updated_at = utcnow()
                updated += 1
            row.source_updated_at = projection.source_updated_at
            session.add(row)
    for row in existing.values():
        session.delete(row)
    session.flush()
    return PassageChanges(inserted=inserted, updated=updated, removed=len(existing))

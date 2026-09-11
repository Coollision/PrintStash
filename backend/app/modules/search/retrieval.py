"""Bounded authorized lexical retrieval; optional semantic legs join here."""

from __future__ import annotations

import re

from printstash_core.search.lexical import query_terms
from printstash_core.search.passages import SubjectType
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from app.db.models import SearchPassage, User
from app.modules.library.model_views.listing import read_items_by_ids
from app.modules.search import cursors
from app.modules.search.access import visible_passage_ids
from app.modules.search.dependencies import SUBJECT_MODELS
from app.modules.search.lexical_index import capability
from app.modules.search.lexical_query import ordered_passages
from app.schemas.search import SearchEvidence, SearchResponse, SearchResult

MAX_CANDIDATES = 2048


def evidence(passage: SearchPassage, query: str) -> SearchEvidence:
    tokens = query_terms(query)
    fields = (
        ("title", passage.title),
        ("tags", passage.tags_text),
        ("text", passage.text),
    )
    field, content = next(
        (
            (name, text)
            for name, text in fields
            if any(token in text.lower() for token in tokens)
        ),
        fields[-1],
    )
    pattern = (
        re.compile("|".join(re.escape(token) for token in tokens), re.IGNORECASE)
        if tokens
        else None
    )
    match = pattern.search(content) if pattern else None
    start = max(0, match.start() - 80) if match else 0
    excerpt = content[start : start + 240]
    ranges = (
        [(match.start(), match.end()) for match in pattern.finditer(excerpt)][:32]
        if pattern
        else []
    )
    return SearchEvidence(field=field, text=excerpt, ranges=ranges)


def search(
    session: Session,
    user: User,
    query: str,
    *,
    mode: str = "hybrid",
    limit: int = 30,
    cursor: str | None = None,
) -> SearchResponse:
    if not 1 <= limit <= 100:
        raise ValueError("search_page_limit")
    query_terms(query)
    context = cursors.context_key(int(user.id), query, mode)
    offset = cursors.decode(cursor, context) if cursor else 0
    backend = capability(session)
    allowed = visible_passage_ids(session, user)
    degraded = []
    try:
        with session.begin_nested():
            ranks = session.exec(
                ordered_passages(session, query, allowed, limit=MAX_CANDIDATES)
            ).all()
    except DBAPIError:
        ranks = session.exec(
            ordered_passages(
                session, query, allowed, limit=MAX_CANDIDATES, force_like=True
            )
        ).all()
        backend = "ranked_like"
        degraded.append("search_fts_unavailable")
    ids = [id for id, _score in ranks]
    passages = (
        {
            row.id: row
            for row in session.exec(
                select(SearchPassage).where(
                    SearchPassage.id.in_(ids), SearchPassage.id.in_(allowed)
                )
            ).all()
        }
        if ids
        else {}
    )
    seen = set()
    unique = []
    for id, _score in ranks:
        passage = passages.get(id)
        if passage is None:
            continue
        subject = passage.subject_type, passage.subject_id
        if subject not in seen:
            seen.add(subject)
            unique.append(passage)
    selected = unique[offset : offset + limit]
    model_ids = [row.subject_id for row in selected if row.subject_type == "model"]
    model_views = {row.id: row for row in read_items_by_ids(session, user, model_ids)}
    items = []
    for passage in selected:
        kind = SubjectType(passage.subject_type)
        row = session.get(SUBJECT_MODELS[kind], passage.subject_id)
        if row is None:
            continue
        href = {
            SubjectType.MODEL: f"/models/{passage.subject_id}",
            SubjectType.COLLECTION: f"/?collection={getattr(row, 'path', '')}",
            SubjectType.DOCUMENT: f"/documents/{passage.subject_id}",
            SubjectType.MULTIPART_MODEL: f"/multipart-models/{passage.subject_id}",
        }[kind]
        items.append(
            SearchResult(
                subject_type=kind,
                subject_id=passage.subject_id,
                name=row.name,
                href=href,
                evidence=[evidence(passage, query)],
                model=model_views.get(passage.subject_id)
                if kind is SubjectType.MODEL
                else None,
            )
        )
    next_cursor = (
        cursors.encode(context, offset + limit)
        if len(unique) > offset + limit
        else None
    )
    return SearchResponse(
        items=items, next_cursor=next_cursor, lexical_backend=backend, degraded=degraded
    )

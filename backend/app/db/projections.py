"""Optional content projections, invoked inside the content owner's transaction.

The contract has no search dependency. Bootstrap installs a projection; domain
operations publish source identities after staging their content changes. The
projection may flush but must never commit, perform inference, or publish events.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from sqlmodel import Session


@dataclass(frozen=True, order=True)
class ContentSource:
    kind: str
    id: int


class ContentProjection(Protocol):
    def refresh(self, session: Session, sources: tuple[ContentSource, ...]) -> None: ...


_projection: ContentProjection | None = None


def bind_content_projection(
    projection: ContentProjection | None,
) -> ContentProjection | None:
    global _projection
    previous = _projection
    _projection = projection
    return previous


def content_changed(session: Session, kind: str, ids: Iterable[int | None]) -> None:
    """Project staged source edits atomically; no-op when the feature is absent."""
    if _projection is None:
        return
    # Evaluate lazy row identities after INSERT has assigned their primary keys.
    session.flush()
    sources = tuple(sorted({ContentSource(kind, id) for id in ids if id is not None}))
    if sources:
        _projection.refresh(session, sources)

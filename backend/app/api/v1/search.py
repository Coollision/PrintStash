"""Search requires a signed-in user; share capabilities never cross this boundary."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from printstash_core.search.passages import SubjectType
from sqlmodel import Session

from app.core.security import get_current_user, oauth2_scheme
from app.db.models import User
from app.db.session import get_session
from app.modules.search.retrieval import search
from app.schemas.search import SearchResponse, SearchStatus

router = APIRouter(prefix="/search", tags=["search"])


def require_search_user(
    user: User | None = Depends(get_current_user),
    credential: str | None = Depends(oauth2_scheme),
) -> User:
    if user is None:
        # An opaque share credential authorizes only its share route. This
        # uniform rejection does not look up or reveal whether a share exists.
        raise HTTPException(
            status_code=403 if credential else 401, detail="search_user_required"
        )
    return user


@router.get("/status", response_model=SearchStatus)
def search_status(
    user: User = Depends(require_search_user), session: Session = Depends(get_session)
):
    from app.modules.search.status import read

    return read(session, user)


@router.get("", response_model=SearchResponse)
def search_library(
    q: str = Query("", max_length=512),
    mode: Literal["lexical", "hybrid"] = "hybrid",
    limit: int = Query(30, ge=1, le=100),
    cursor: str | None = Query(None, max_length=512),
    types: list[SubjectType] | None = Query(None, alias="types[]", max_length=4),
    legs: list[Literal["lexical", "semantic_text"]] | None = Query(
        None, alias="legs[]", max_length=2
    ),
    instant: bool = False,
    user: User = Depends(require_search_user),
    session: Session = Depends(get_session),
) -> SearchResponse:
    return search(
        session,
        user,
        q,
        mode=mode,
        limit=limit,
        cursor=cursor,
        types=tuple(types) if types is not None else tuple(SubjectType),
        legs=tuple(legs) if legs is not None else ("lexical", "semantic_text"),
        instant=instant,
    )

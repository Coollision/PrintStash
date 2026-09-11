"""Administrator-only AI configuration; ordinary queries never accept endpoints."""

from fastapi import APIRouter, Depends
from printstash_core.inference import EmbeddingError
from sqlmodel import Session

from app.core.errors import ErrorKind, OperationError
from app.core.security import get_current_user, require_superuser
from app.db.models import User
from app.db.session import get_session
from app.modules.inference.configuration import create
from app.modules.search import configuration, generations
from app.schemas.inference import (
    EndpointProposal,
    EndpointRead,
    SearchSettings,
    SearchSettingsRead,
)
from app.schemas.search_generations import (
    GenerationAction,
    GenerationProposal,
    GenerationRead,
)

router = APIRouter(
    prefix="/config/ai-search",
    tags=["config"],
    dependencies=[Depends(require_superuser)],
)


@router.get("", response_model=SearchSettingsRead)
def read_settings(session: Session = Depends(get_session)):
    return configuration.read(session)


@router.put("", response_model=SearchSettingsRead)
def update_settings(body: SearchSettings, session: Session = Depends(get_session)):
    return configuration.update(session, body)


@router.post("/endpoints", response_model=EndpointRead, status_code=201)
def create_endpoint(body: EndpointProposal, session: Session = Depends(get_session)):
    return create(session, body)


@router.get("/generations", response_model=list[GenerationRead])
def read_generations(session: Session = Depends(get_session)):
    return generations.list_generations(session)


@router.post("/generations", response_model=GenerationRead, status_code=202)
def propose_generation(
    body: GenerationProposal,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    try:
        return generations.prepare(session, user, body)
    except EmbeddingError as exc:
        raise OperationError(exc.code, kind=ErrorKind.INVALID) from None


@router.post("/generations/{generation_id}/activate", response_model=GenerationRead)
def activate_generation(
    generation_id: int, body: GenerationAction, session: Session = Depends(get_session)
):
    return generations.activate(session, generation_id, body.version_token)


@router.post("/generations/{generation_id}/cancel", response_model=GenerationRead)
def cancel_generation(
    generation_id: int, body: GenerationAction, session: Session = Depends(get_session)
):
    return generations.cancel(session, generation_id, body.version_token)


@router.post("/generations/{generation_id}/retry", response_model=GenerationRead)
def retry_generation(
    generation_id: int, body: GenerationAction, session: Session = Depends(get_session)
):
    return generations.retry_quarantine(session, generation_id, body.version_token)

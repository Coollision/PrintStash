"""Administrator-only AI configuration; ordinary queries never accept endpoints."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.security import require_superuser
from app.db.session import get_session
from app.modules.inference.configuration import create
from app.modules.search import configuration
from app.schemas.inference import (
    EndpointProposal,
    EndpointRead,
    SearchSettings,
    SearchSettingsRead,
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

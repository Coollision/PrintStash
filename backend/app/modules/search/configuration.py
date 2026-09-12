"""Independent opt-ins for retrieval, local models, captions and NL filters."""

from sqlmodel import Session

from app.core.errors import ErrorKind, OperationError
from app.db.models import InferenceEndpoint, SystemConfig
from app.modules.administration import audit
from app.modules.administration.config_repository import get_or_create
from app.modules.inference.configuration import list_endpoints
from app.modules.inference.environment import configured
from app.schemas.inference import SearchSettings, SearchSettingsRead


def settings(session: Session) -> SearchSettings:
    row = session.get(SystemConfig, 1)
    return (
        SearchSettings.model_validate_json(row.ai_search_settings_json)
        if row and row.ai_search_settings_json
        else SearchSettings()
    )


def read(session: Session) -> SearchSettingsRead:
    return SearchSettingsRead(
        settings=settings(session),
        endpoints=list_endpoints(session),
        environment_endpoints=configured(),
    )


def update(session: Session, value: SearchSettings) -> SearchSettingsRead:
    endpoint = (
        session.get(InferenceEndpoint, value.chat_endpoint_id)
        if value.chat_endpoint_id
        else None
    )
    if value.chat_endpoint_id and (endpoint is None or endpoint.kind != "chat"):
        raise OperationError("inference_chat_unavailable", kind=ErrorKind.INVALID)
    if value.nl_filters_enabled and endpoint is None:
        raise OperationError("inference_chat_required", kind=ErrorKind.INVALID)
    if value.captions_enabled and (
        endpoint is None
        or not endpoint.supports_images
        or not value.send_rendered_images
    ):
        raise OperationError(
            "inference_caption_consent_required", kind=ErrorKind.INVALID
        )
    row = get_or_create(session, commit=False)
    row.ai_search_settings_json = value.model_dump_json()
    session.add(row)
    audit.record(
        session,
        action="ai_search_settings_changed",
        resource_type="ai_search",
        diff=value.model_dump(),
    )
    return read(session)

"""Real search workflows share only database setup and a stand-in at HTTP egress."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlmodel import select

from app.db.models import IndexGeneration
from app.db.session import get_session_factory
from app.modules.inference.transport import EndpointError
from app.modules.search import configuration, vector_index
from app.modules.search.indexing import IndexProcessor
from app.schemas.inference import SearchSettings


@pytest.fixture
def generation_setup(db_session, make_user, make_inference_endpoint, make_document):
    actor = make_user(superuser=True)
    endpoint = make_inference_endpoint()
    make_document("Assembly guide", body="Fit the lid")
    configuration.update(db_session, SearchSettings(enabled=True))
    try:
        yield actor, endpoint
    finally:
        db_session.rollback()
        for generation in db_session.exec(select(IndexGeneration)).all():
            generation.state = "retired"
            vector_index.drop(db_session, generation)
        db_session.commit()


@pytest.fixture
def healthy_embeddings():
    state = SimpleNamespace(
        requests=[], poison=None, before_reply=None, dimension=4, vector=None
    )

    def reply(_endpoint, _path, payload, **kwargs):
        state.requests.append(payload)
        if state.before_reply is not None:
            callback, state.before_reply = state.before_reply, None
            callback()
        if state.poison and any(state.poison in value for value in payload["input"]):
            raise EndpointError("inference_request_rejected")
        return {
            "data": [
                {
                    "index": index,
                    "embedding": state.vector
                    if state.vector is not None
                    else [1] + [0] * (state.dimension - 1),
                }
                for index, _ in enumerate(payload["input"])
            ]
        }

    with patch("app.modules.inference.remote.post_json", side_effect=reply):
        yield state


@pytest.fixture
def advance_generation():
    def ready(generation_id: int):
        processor = IndexProcessor(get_session_factory())
        for _ in range(40):
            processor.work_one()
            with get_session_factory().scoped_session() as session:
                generation = session.get(IndexGeneration, generation_id)
                if generation.phase == "ready":
                    return
        raise AssertionError("generation did not become ready")

    return ready


@pytest.fixture
def advance_indexing():
    def advance(count: int):
        return tuple(
            IndexProcessor(get_session_factory()).work_one() for _ in range(count)
        )

    return advance

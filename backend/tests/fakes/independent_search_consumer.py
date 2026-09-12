"""An installed consumer of the public inference/vector seams, without Similar Models."""

import sys
from importlib.util import find_spec

from fastapi.testclient import TestClient
from printstash_core.inference import EmbeddingInput
from sqlalchemy import literal
from sqlmodel import select

from app.core.config import ensure_dirs, settings
from app.db.models import PassageVector, SearchPassage, User
from app.db.session import get_session_factory
from app.main import app
from app.modules.inference.local import configured_provider
from app.modules.search import vector_store
from app.modules.search.access import visible_passage_ids


def run():
    assert find_spec("app.modules.similarity") is None
    ensure_dirs()
    with TestClient(app) as client:
        assert app.state.similarity_task is None
        client.headers["Origin"] = "http://testserver"
        preparation = client.post("/api/v1/setup/session")
        assert preparation.status_code == 200
        client.headers["X-PrintStash-Setup-CSRF"] = preparation.json()["csrf"]
        setup = client.post(
            "/api/v1/setup",
            json={
                "username": "owner",
                "password": "Password123",
                "storage_backend": "local",
                "data_dir": str(settings.data_dir),
                "thumb_dir": str(settings.thumb_dir),
            },
        )
        assert setup.status_code == 201
        client.headers["Authorization"] = "Bearer " + setup.json()["access_token"]
        response = client.post(
            "/api/v1/documents",
            json={"name": "Independent guide", "body": "A red boat"},
        )
        assert response.status_code == 201
        doc_id = response.json()["id"]
        lexical = client.get("/api/v1/search", params={"q": "boat", "mode": "lexical"})
        assert lexical.status_code == 200
        assert any(item["subject_id"] == doc_id for item in lexical.json()["items"])
        sessions = get_session_factory()
        provider = configured_provider(sessions)
        generation_id = vector_store.initialize(sessions, provider)
        vector = provider.embed((EmbeddingInput("text", text="red"),), provider.space)[
            0
        ]
        with sessions.scoped_session() as session:
            actor = session.exec(select(User).where(User.username == "owner")).one()
            passage = session.exec(
                select(SearchPassage).where(
                    SearchPassage.subject_type == "document",
                    SearchPassage.subject_id == doc_id,
                )
            ).one()
            source = select(
                SearchPassage.subject_type,
                SearchPassage.subject_id,
                literal(None).label("model_id"),
                literal(None).label("file_id"),
                SearchPassage.id.label("passage_id"),
            ).where(
                SearchPassage.id == passage.id,
                SearchPassage.content_hash == passage.content_hash,
                SearchPassage.id.in_(visible_passage_ids(session, actor)),
            )
            assert vector_store.publish(
                session,
                generation_id=generation_id,
                space=provider.space,
                unit_kind="independent_passage",
                unit_key=f"independent:{passage.id}",
                input_hash=passage.content_hash,
                vector=vector,
                source=source,
            )
            session.commit()
            original = session.exec(select(PassageVector)).one()
            before = (original.id, original.vector_blob, provider.space.config_hash)
            # The external ranking algorithm is consumer metadata. Changing it
            # does not alter an immutable inference Space or republish native bytes.
            observations = []
            for algorithm_version in ("consumer-ranker-v1", "consumer-ranker-v2"):
                result = vector_store.query(
                    session,
                    generation_id=generation_id,
                    space=provider.space,
                    vector=vector,
                    allowed_ids=select(PassageVector.id).where(
                        PassageVector.passage_id.in_(
                            visible_passage_ids(session, actor)
                        )
                    ),
                )
                observations.append((algorithm_version, result.items[0].subject_id))
            assert observations == [
                ("consumer-ranker-v1", doc_id),
                ("consumer-ranker-v2", doc_id),
            ]
            same = vector_store.register_space(session, provider.space)
            assert same.config_hash == before[2]
            assert (original.id, original.vector_blob) == before[:2]
        assert not any(
            name == "app.modules.similarity"
            or name.startswith("app.modules.similarity.")
            for name in sys.modules
        )
    print("independent-search-consumer-complete")


if __name__ == "__main__":
    run()

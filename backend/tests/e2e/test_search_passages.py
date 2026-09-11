"""The passage foundation can materialize real API-created library Documents.

Projection is explicitly invoked until W1's mutation port is installed; this
flow proves durable source extraction, not automatic indexing or retrieval.
"""

import pytest
from printstash_core.search.passages import SearchSubject, SubjectType
from sqlmodel import select

from app.db.models.search import SearchPassage
from app.db.session import get_session_factory
from app.modules.search.passages import sync_subject


class TestSearchPassageLifecycle:
    @pytest.mark.asyncio
    async def test_materializes_a_document_created_through_the_api(
        self, api, superuser_headers
    ):
        response = await api.post(
            "/api/v1/documents",
            headers=superuser_headers,
            json={"name": "Assembly guide", "body": "Slide the lid into the box."},
        )
        assert response.status_code == 201, response.text
        subject = SearchSubject(SubjectType.DOCUMENT, response.json()["id"])

        with get_session_factory().scoped_session() as session:
            sync_subject(session, subject)
            session.commit()

        with get_session_factory().scoped_session() as session:
            assert session.exec(select(SearchPassage.text)).all() == [
                "Title: Assembly guide\nBody: Slide the lid into the box."
            ]

"""Search never broadens an authenticated user's library permissions."""

import pytest
from sqlalchemy import delete

from app.db.models import CollectionPermission, CollectionRole
from app.db.projections import bind_content_projection, content_changed
from app.modules.search.lexical_index import rebuild_partition
from app.modules.search.projection import LibraryProjection
from tests.factories import bearer


@pytest.fixture(autouse=True)
def projection():
    previous = bind_content_projection(LibraryProjection())
    yield
    bind_content_projection(previous)


class TestSearch:
    @pytest.mark.parametrize("mode", ["anonymous", "disabled", "busy"])
    def test_rejects_image_requests_before_reading_the_body(
        self, client, db_session, make_user, monkeypatch, mode
    ):
        import threading

        from app.api.v1 import search as route
        from app.modules.search import configuration
        from app.schemas.inference import SearchSettings

        actor = make_user(superuser=True)
        configuration.update(db_session, SearchSettings(enabled=mode != "disabled"))
        db_session.commit()
        slots = threading.BoundedSemaphore(2)
        if mode == "busy":
            slots.acquire()
            slots.acquire()
        monkeypatch.setattr(route, "_image_slots", slots)

        async def no_body(*args):
            raise AssertionError("unauthorized or unadmitted body was parsed")

        monkeypatch.setattr(route, "read_image", no_body)
        response = client.post(
            "/api/v1/search/image",
            content=b"untrusted image",
            headers={} if mode == "anonymous" else bearer(actor),
        )
        assert (
            response.status_code
            == {"anonymous": 401, "disabled": 409, "busy": 429}[mode]
        ), response.text

    def test_uses_the_configured_ranked_like_backend(
        self, client, db_session, auth_headers, make_model
    ):
        model = make_model("Bracket")
        content_changed(db_session, "model", [model.id])
        rebuild_partition(db_session)
        db_session.commit()
        assert (
            client.patch(
                "/api/v1/search/settings",
                headers=auth_headers,
                json={"lexical_backend": "ranked_like"},
            ).status_code
            == 200
        )
        response = client.get(
            "/api/v1/search", headers=auth_headers, params={"q": "bracket"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["lexical_backend"] == "ranked_like"
        assert response.json()["items"][0]["subject_id"] == model.id

    def test_links_collection_matches_to_the_existing_browse_route(
        self, client, db_session, auth_headers, make_collection
    ):
        collection = make_collection("Bracket tools")
        content_changed(db_session, "collection", [collection.id])
        db_session.commit()
        response = client.get(
            "/api/v1/search", headers=auth_headers, params={"q": "bracket"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["href"] == "/?c=bracket-tools"

    def test_reports_lexical_status_with_ai_disabled(self, client, auth_headers):
        response = client.get("/api/v1/search/status", headers=auth_headers)

        assert response.status_code == 200, response.text
        assert response.json() == {
            "enabled": False,
            "semantic_ready": False,
            "legs": ["lexical"],
            "generations": [],
            "degraded": [],
            "backlog": False,
            "remote_hosts": [],
        }

    def test_requires_authentication_for_status(self, client):
        assert client.get("/api/v1/search/status").status_code == 401

    def test_rejects_unauthenticated_search(self, client):
        response = client.get("/api/v1/search", params={"q": "private"})
        assert response.status_code == 401

    def test_rejects_share_context_search(self, client, db_session, make_model):
        from app.modules.identity.share import create_share

        model = make_model()
        _link, token = create_share(
            db_session,
            model_id=model.id,
            expires_in_days=1,
            allow_download=False,
            created_by=None,
        )
        response = client.get(
            "/api/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": "bracket"},
        )
        assert response.status_code == 403

    def test_hides_unauthorized_member_segments(
        self,
        client,
        db_session,
        make_user,
        make_model,
        make_collection,
        make_multipart_model,
        grant_role,
    ):
        admin = make_user(superuser=True)
        viewer = make_user()
        public = make_collection("Shared")
        private = make_collection("Private")
        member = make_model("Secretprototype", collection=private)
        aggregate = make_multipart_model("Assembly", collection=public)
        grant_role(viewer, public, CollectionRole.VIEW)
        response = client.put(
            f"/api/v1/multipart-models/{aggregate.id}",
            headers=bearer(admin),
            json={"parts": [{"name": "Leg", "choices": [{"model_id": member.id}]}]},
        )
        assert response.status_code == 200, response.text
        content_changed(db_session, "model", [member.id])
        rebuild_partition(db_session)
        db_session.commit()

        response = client.get(
            "/api/v1/search", headers=bearer(viewer), params={"q": "Secretprototype"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["items"] == []
        response = client.get(
            "/api/v1/search", headers=bearer(viewer), params={"q": "Assembly"}
        )
        assert [row["subject_id"] for row in response.json()["items"]] == [aggregate.id]

    def test_applies_permission_revocation_immediately(
        self, client, db_session, make_user, make_model, make_collection, grant_role
    ):
        viewer = make_user()
        collection = make_collection("Shared")
        model = make_model("Bracket", collection=collection)
        grant_role(viewer, collection, CollectionRole.VIEW)
        content_changed(db_session, "model", [model.id])
        rebuild_partition(db_session)
        db_session.commit()
        assert client.get(
            "/api/v1/search", headers=bearer(viewer), params={"q": "bracket"}
        ).json()["items"]
        db_session.exec(
            delete(CollectionPermission).where(
                CollectionPermission.user_id == viewer.id
            )
        )
        db_session.commit()

        response = client.get(
            "/api/v1/search", headers=bearer(viewer), params={"q": "bracket"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["items"] == []

    def test_returns_bounded_plain_text_evidence(
        self, client, db_session, make_user, make_document
    ):
        actor = make_user(superuser=True)
        doc = make_document(
            "Guide", body='<script>alert("assembly")</script>' + "x " * 300
        )
        content_changed(db_session, "document", [doc.id])
        rebuild_partition(db_session)
        db_session.commit()

        response = client.get(
            "/api/v1/search", headers=bearer(actor), params={"q": "assembly"}
        )

        assert response.status_code == 200, response.text
        evidence = response.json()["items"][0]["evidence"][0]
        assert len(evidence["text"]) <= 240
        start, end = evidence["ranges"][0]
        assert evidence["text"][start:end] == "assembly"
        assert "<mark>" not in evidence["text"]

    def test_rejects_a_cursor_from_another_query(
        self, client, db_session, make_user, make_model
    ):
        actor = make_user(superuser=True)
        models = [make_model(f"Bracket {i}") for i in range(3)]
        content_changed(db_session, "model", [row.id for row in models])
        db_session.commit()
        first = client.get(
            "/api/v1/search", headers=bearer(actor), params={"q": "bracket", "limit": 1}
        ).json()
        assert first["next_cursor"]

        response = client.get(
            "/api/v1/search",
            headers=bearer(actor),
            params={"q": "hinge", "cursor": first["next_cursor"]},
        )

        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "search_cursor_invalid"

    def test_paginates_without_repeating_a_subject(
        self, client, db_session, make_user, make_model
    ):
        actor = make_user(superuser=True)
        models = [make_model(f"Bracket {i}") for i in range(3)]
        content_changed(db_session, "model", [row.id for row in models])
        db_session.commit()
        first = client.get(
            "/api/v1/search", headers=bearer(actor), params={"q": "bracket", "limit": 2}
        ).json()
        second = client.get(
            "/api/v1/search",
            headers=bearer(actor),
            params={"q": "bracket", "limit": 2, "cursor": first["next_cursor"]},
        ).json()

        assert [row["subject_id"] for row in first["items"] + second["items"]] == [
            row.id for row in models
        ]
        assert second["next_cursor"] is None

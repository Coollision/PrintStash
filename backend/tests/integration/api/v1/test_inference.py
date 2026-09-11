"""Only administrators can add probed endpoints; credentials stay encrypted and redacted."""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlmodel import select

from app.db.models import AuditLog, IndexGeneration, InferenceEndpoint
from app.modules.inference.configuration import load

PROPOSAL = {
    "base_url": "http://inference.local:11434/v1",
    "model": "test-embedding",
    "kind": "embedding",
    "native_dimension": 4,
    "api_key": "test-api-key",
    "headers": {"X-Test-Token": "test-header-secret"},
}


@pytest.fixture
def embedding_endpoint():
    with patch(
        "app.modules.inference.remote.post_json",
        return_value={"data": [{"index": 0, "embedding": [1, 0, 0, 0]}]},
    ):
        yield


class TestCreateEndpoint:
    def test_reports_a_probed_endpoint(self, client, auth_headers, embedding_endpoint):
        response = client.post(
            "/api/v1/config/ai-search/endpoints", json=PROPOSAL, headers=auth_headers
        )

        assert response.status_code == 201, response.text
        assert response.json() == {
            "id": 1,
            "kind": "embedding",
            "host": "inference.local",
            "model": "test-embedding",
            "revision": "configured-v1",
            "config_hash": response.json()["config_hash"],
            "native_dimension": 4,
            "supports_images": False,
            "dialect": None,
            "guarantee": None,
            "has_credentials": True,
        }

    def test_keeps_inference_credentials_encrypted(
        self, client, auth_headers, embedding_endpoint, db_session
    ):
        response = client.post(
            "/api/v1/config/ai-search/endpoints", json=PROPOSAL, headers=auth_headers
        )
        assert response.status_code == 201, response.text

        raw = db_session.exec(
            text("SELECT api_key, headers_json, config_json FROM inference_endpoints")
        ).one()
        assert "test-api-key" not in str(raw)
        assert "test-header-secret" not in str(raw)
        assert (
            load(
                db_session.get(InferenceEndpoint, response.json()["id"])
            ).request_headers()["X-Test-Token"]
            == "test-header-secret"
        )

    def test_omits_credentials_from_audit(
        self, client, auth_headers, embedding_endpoint, db_session
    ):
        response = client.post(
            "/api/v1/config/ai-search/endpoints", json=PROPOSAL, headers=auth_headers
        )
        assert response.status_code == 201, response.text

        records = db_session.exec(
            select(AuditLog).where(AuditLog.action == "inference_endpoint_created")
        ).all()

        assert [json.loads(record.diff_json) for record in records] == [
            {"kind": "embedding", "host": "inference.local", "model": "test-embedding"}
        ]

    def test_requires_admin_endpoint_configuration(
        self, client, user_headers, db_session
    ):
        response = client.post(
            "/api/v1/config/ai-search/endpoints", json=PROPOSAL, headers=user_headers()
        )

        assert response.status_code == 403, response.text
        assert db_session.exec(select(InferenceEndpoint)).all() == []

    def test_isolates_endpoint_configuration_versions(
        self, client, auth_headers, embedding_endpoint, db_session
    ):
        first = client.post(
            "/api/v1/config/ai-search/endpoints", json=PROPOSAL, headers=auth_headers
        )
        assert first.status_code == 201, first.text

        second = client.post(
            "/api/v1/config/ai-search/endpoints",
            json=PROPOSAL | {"api_key": "test-replacement-key"},
            headers=auth_headers,
        )

        assert second.status_code == 201, second.text
        assert first.json()["config_hash"] != second.json()["config_hash"]
        assert (
            load(
                db_session.get(InferenceEndpoint, first.json()["id"])
            ).api_key.get_secret_value()
            == "test-api-key"
        )

    def test_rejects_wrong_canary_dimension(
        self, client, auth_headers, embedding_endpoint, db_session
    ):
        response = client.post(
            "/api/v1/config/ai-search/endpoints",
            json=PROPOSAL | {"native_dimension": 8},
            headers=auth_headers,
        )

        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "embedding_dimension_mismatch"
        assert db_session.exec(select(InferenceEndpoint)).all() == []

    def test_redacts_invalid_configuration_input(self, client, auth_headers):
        response = client.post(
            "/api/v1/config/ai-search/endpoints",
            json=PROPOSAL | {"headers": {"Host": "test-secret-invalid-header"}},
            headers=auth_headers,
        )

        assert response.status_code == 422, response.text
        assert "test-api-key" not in response.text
        assert "test-secret-invalid-header" not in response.text

    def test_refuses_client_supplied_configuration_versions(self, client, auth_headers):
        response = client.post(
            "/api/v1/config/ai-search/endpoints",
            json=PROPOSAL | {"configuration_version": "a" * 32},
            headers=auth_headers,
        )

        assert response.status_code == 422, response.text


class TestReadSettings:
    def test_defaults_to_independent_opt_ins(self, client, auth_headers):
        response = client.get("/api/v1/config/ai-search", headers=auth_headers)

        assert response.status_code == 200, response.text
        assert response.json() == {
            "settings": {
                "enabled": False,
                "captions_enabled": False,
                "nl_filters_enabled": False,
                "local_models_enabled": False,
                "send_rendered_images": False,
                "send_query_images": False,
                "chat_endpoint_id": None,
                "rollback_retention_hours": 24,
                "max_index_bytes": 2147483648,
            },
            "endpoints": [],
        }

    def test_discloses_hosts_without_credentials(
        self, client, auth_headers, embedding_endpoint
    ):
        created = client.post(
            "/api/v1/config/ai-search/endpoints", json=PROPOSAL, headers=auth_headers
        )
        assert created.status_code == 201, created.text

        response = client.get("/api/v1/config/ai-search", headers=auth_headers)

        assert response.json()["endpoints"][0]["host"] == "inference.local"
        assert "test-api-key" not in response.text
        assert "test-header-secret" not in response.text

    def test_hides_administrative_hosts_from_regular_users(self, client, user_headers):
        response = client.get("/api/v1/config/ai-search", headers=user_headers())

        assert response.status_code == 403, response.text


class TestUpdateSettings:
    def test_persists_retrieval_opt_in(self, client, auth_headers):
        response = client.put(
            "/api/v1/config/ai-search", json={"enabled": True}, headers=auth_headers
        )

        assert response.status_code == 200, response.text
        assert (
            client.get("/api/v1/config/ai-search", headers=auth_headers).json()[
                "settings"
            ]["enabled"]
            is True
        )

    @pytest.mark.parametrize(
        "field", ["captions_enabled", "nl_filters_enabled"], ids=["captions", "nl"]
    )
    def test_requires_a_capable_chat_endpoint(self, client, auth_headers, field):
        response = client.put(
            "/api/v1/config/ai-search", json={field: True}, headers=auth_headers
        )

        assert response.status_code == 400, response.text
        assert (
            client.get("/api/v1/config/ai-search", headers=auth_headers).json()[
                "settings"
            ][field]
            is False
        )

    def test_requires_admin_settings_changes(self, client, user_headers):
        response = client.put(
            "/api/v1/config/ai-search", json={"enabled": True}, headers=user_headers()
        )

        assert response.status_code == 403, response.text


class TestProposeGeneration:
    def test_exposes_a_durable_build_job(
        self, client, auth_headers, make_inference_endpoint
    ):
        endpoint = make_inference_endpoint()
        enabled = client.put(
            "/api/v1/config/ai-search", headers=auth_headers, json={"enabled": True}
        )
        assert enabled.status_code == 200, enabled.text

        response = client.post(
            "/api/v1/config/ai-search/generations",
            headers=auth_headers,
            json={"endpoint_id": endpoint.id, "index_backend": "numpy"},
        )

        assert response.status_code == 202, response.text
        assert response.json()["state"] == "building"
        assert response.json()["job_id"]
        listed = client.get(
            "/api/v1/config/ai-search/generations", headers=auth_headers
        )
        assert listed.json() == [response.json()]

    def test_rejects_unavailable_recipes(
        self, client, auth_headers, make_inference_endpoint
    ):
        endpoint = make_inference_endpoint()
        enabled = client.put(
            "/api/v1/config/ai-search", headers=auth_headers, json={"enabled": True}
        )
        assert enabled.status_code == 200, enabled.text

        response = client.post(
            "/api/v1/config/ai-search/generations",
            headers=auth_headers,
            json={"endpoint_id": endpoint.id, "passage_recipe_version": 999},
        )

        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "search_recipe_unavailable"

    def test_requires_admin_generation_proposals(
        self, client, user_headers, db_session
    ):
        response = client.post(
            "/api/v1/config/ai-search/generations",
            headers=user_headers(),
            json={"endpoint_id": 1},
        )

        assert response.status_code == 403, response.text
        assert db_session.exec(select(IndexGeneration)).all() == []


class TestCancelGeneration:
    def test_cancels_the_selected_proposal(
        self, client, auth_headers, make_inference_endpoint
    ):
        endpoint = make_inference_endpoint()
        enabled = client.put(
            "/api/v1/config/ai-search", headers=auth_headers, json={"enabled": True}
        )
        assert enabled.status_code == 200, enabled.text
        proposal = client.post(
            "/api/v1/config/ai-search/generations",
            headers=auth_headers,
            json={"endpoint_id": endpoint.id, "index_backend": "numpy"},
        ).json()

        response = client.post(
            f"/api/v1/config/ai-search/generations/{proposal['id']}/cancel",
            headers=auth_headers,
            json={"version_token": proposal["version_token"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["state"] == "cancelled"

    @pytest.mark.parametrize(
        "action", ["activate", "cancel", "retry"], ids=["activate", "cancel", "retry"]
    )
    def test_requires_admin_generation_actions(self, client, user_headers, action):
        response = client.post(
            f"/api/v1/config/ai-search/generations/1/{action}",
            headers=user_headers(),
            json={"version_token": "a" * 32},
        )

        assert response.status_code == 403, response.text

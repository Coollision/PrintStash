"""Model configuration keeps credentials and filesystem paths out of responses."""

import pytest

from app.core.config import _overlay
from app.modules.inference import model_cache
from tests.factories.embeddings import text_embedding_assets


class TestInferenceModels:
    def test_reports_local_unavailable_while_offering_remote(
        self, client, auth_headers, monkeypatch, make_inference_endpoint
    ):
        from app.api.v1 import inference_models

        endpoint = make_inference_endpoint()
        monkeypatch.setattr(
            inference_models.importlib.util, "find_spec", lambda name: None
        )
        response = client.get("/api/v1/inference/models", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() and all(
            not row["runtime_available"] for row in response.json()
        )
        response = client.get("/api/v1/config/ai-search", headers=auth_headers)
        assert response.status_code == 200
        assert any(row["id"] == endpoint.id for row in response.json()["endpoints"])

    @pytest.mark.parametrize(
        "method, path",
        [
            ("get", "/inference/models"),
            ("post", "/inference/models/bge-small-en-v1.5/download"),
            ("post", "/inference/models/invalid/validate"),
            ("delete", "/inference/models/invalid"),
        ],
    )
    def test_rejects_nonadministrator_model_management(
        self, client, make_user, method, path
    ):
        from app.modules.identity.auth import create_access_token

        user = make_user(superuser=False)
        token = create_access_token(user.id, user.username, scope="admin")
        response = getattr(client, method)(
            "/api/v1" + path, headers={"Authorization": "Bearer " + token}
        )
        assert response.status_code == 403

    def test_rejects_unsupported_local_runtime_before_download(
        self, client, auth_headers, monkeypatch, tmp_path
    ):
        from app.runtime import model_acquisition

        root = tmp_path / "uncreated"
        monkeypatch.setitem(_overlay, "embedding_cache_dir", root)
        assert (
            client.put(
                "/api/v1/config/ai-search",
                headers=auth_headers,
                json={
                    "enabled": True,
                    "local_models_enabled": True,
                    "download_enabled": True,
                },
            ).status_code
            == 200
        )
        monkeypatch.setattr(
            model_acquisition.importlib.util, "find_spec", lambda name: None
        )
        response = client.post(
            "/api/v1/inference/models/bge-small-en-v1.5/download", headers=auth_headers
        )
        assert response.status_code == 409
        assert "embedding_runtime_unavailable" in response.text
        assert not root.exists()

    def test_lists_preplaced_models_without_downloads(
        self, client, auth_headers, tmp_path, monkeypatch
    ):
        root = tmp_path / "cache"
        directory = text_embedding_assets(root / "preplaced")
        monkeypatch.setitem(_overlay, "embedding_cache_dir", root)
        monkeypatch.setitem(_overlay, "embedding_local_model_dir", "")
        identity = model_cache.inspect(directory).id
        response = client.get("/api/v1/inference/models", headers=auth_headers)
        assert response.status_code == 200
        row = next(row for row in response.json() if row["id"] == identity)
        assert row["installed"] and row["runtime_available"]
        assert row["license"] == "CC0-1.0"
        assert str(tmp_path) not in response.text

    @pytest.mark.parametrize(
        "flags",
        [{}, {"enabled": True}, {"enabled": True, "local_models_enabled": True}],
    )
    def test_never_downloads_without_acquisition_opt_in(
        self, client, auth_headers, flags, tmp_path, monkeypatch
    ):
        root = tmp_path / "uncreated-cache"
        monkeypatch.setitem(_overlay, "embedding_cache_dir", root)
        assert (
            client.put(
                "/api/v1/config/ai-search", headers=auth_headers, json=flags
            ).status_code
            == 200
        )
        response = client.post(
            "/api/v1/inference/models/bge-small-en-v1.5/download", headers=auth_headers
        )
        assert response.status_code == 409
        assert not root.exists()

    @pytest.mark.parametrize(
        "method, path",
        [
            ("get", "/inference/models"),
            ("post", "/inference/models/bge-small-en-v1.5/download"),
            ("post", "/inference/models/invalid/validate"),
            ("delete", "/inference/models/invalid"),
        ],
    )
    def test_rejects_unauthenticated_model_management(self, client, method, path):
        response = getattr(client, method)("/api/v1" + path)
        assert response.status_code in {401, 403}

"""Stored endpoint versions select providers without mutating serving configuration."""

import pytest
from printstash_core.inference import EmbeddingError, EmbeddingSpace

from app.modules.inference import configuration


class TestEmbeddingProvider:
    def test_loads_the_exact_endpoint_version(
        self, db_session, make_inference_endpoint
    ):
        endpoint = make_inference_endpoint()
        config = configuration.load(endpoint)
        space = EmbeddingSpace(
            model_key=config.model,
            model_revision=config.revision,
            dimension=endpoint.native_dimension,
            modality="text",
            render_recipe="v1",
            provider="openai_compatible",
            provider_config_hash=config.identity,
        )

        provider = configuration.embedding_provider(db_session, space)

        assert provider.space == space
        assert provider.endpoint.identity == config.identity

    def test_rejects_a_missing_endpoint_version(
        self, db_session, make_inference_endpoint
    ):
        endpoint = make_inference_endpoint()
        config = configuration.load(endpoint)
        space = EmbeddingSpace(
            model_key=config.model,
            model_revision=config.revision,
            dimension=4,
            modality="text",
            render_recipe="v1",
            provider="openai_compatible",
            provider_config_hash="f" * 64,
        )

        with pytest.raises(EmbeddingError, match="inference_endpoint_unavailable"):
            configuration.embedding_provider(db_session, space)


class TestChatProvider:
    def test_loads_probed_chat_capabilities(self, db_session, make_inference_endpoint):
        endpoint = make_inference_endpoint(kind="chat", supports_images=True)

        provider = configuration.chat_provider(db_session, endpoint.id)

        assert provider.supports_images is True
        assert provider.endpoint.identity == endpoint.config_hash

    def test_rejects_embedding_endpoints_as_chat(
        self, db_session, make_inference_endpoint
    ):
        endpoint = make_inference_endpoint()

        with pytest.raises(EmbeddingError, match="inference_chat_unavailable"):
            configuration.chat_provider(db_session, endpoint.id)


class TestLoad:
    def test_rejects_corrupt_configuration_identities(
        self, db_session, make_inference_endpoint
    ):
        endpoint = make_inference_endpoint(config_hash="a" * 64)

        with pytest.raises(EmbeddingError, match="inference_configuration_mismatch"):
            configuration.load(endpoint)

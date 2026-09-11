"""Structured chat works across schema, tool and strict-JSON endpoint dialects."""

import pytest
from printstash_core.inference import EmbeddingError
from printstash_core.inference.chat import ChatInput
from printstash_core.inference.context import InferenceContext

from app.modules.inference.chat import RemoteChatProvider
from app.modules.inference.endpoint import EndpointConfig
from app.modules.inference.transport import close_client
from tests.fakes.inference import InferenceFake
from tests.fakes.server import start_server

REQUEST = ChatInput(
    instruction="Describe the subject.",
    text="Small boat",
    schema={
        "type": "object",
        "properties": {"caption": {"type": "string", "maxLength": 100}},
        "required": ["caption"],
        "additionalProperties": False,
    },
)


@pytest.fixture
def chat_endpoint():
    fake = InferenceFake()
    running = start_server(fake.app())
    provider = RemoteChatProvider(
        EndpointConfig(base_url=running.base_url + "/v1", model=fake.model)
    )
    try:
        yield fake, provider
    finally:
        close_client()
        running.stop()


class TestRemoteChatProvider:
    def test_probes_responses_without_assuming_availability(self, chat_endpoint):
        fake, original = chat_endpoint
        provider = RemoteChatProvider(
            original.endpoint.model_copy(update={"prefer_responses": True})
        )

        result = provider.complete(REQUEST)

        assert result.dialect == "json_schema"
        assert [call["path"] for call in fake.calls] == ["responses", "chat"]

    def test_uses_a_confirmed_responses_endpoint(self, chat_endpoint):
        fake, original = chat_endpoint
        fake.responses_available = True
        provider = RemoteChatProvider(
            original.endpoint.model_copy(update={"prefer_responses": True})
        )

        result = provider.complete(REQUEST)

        assert (result.value, result.dialect, result.guarantee) == (
            {"caption": "A small boat"},
            "responses",
            "schema_constrained",
        )
        assert fake.calls[0]["body"]["store"] is False

    def test_does_not_fall_back_after_a_responses_timeout(self, chat_endpoint):
        fake, original = chat_endpoint
        fake.responses_available = True
        fake.fault = "timeout"
        provider = RemoteChatProvider(
            original.endpoint.model_copy(update={"prefer_responses": True})
        )

        with pytest.raises(EmbeddingError, match="inference_timeout"):
            provider.complete(REQUEST, context=InferenceContext.bounded(0.3))

        assert [call["path"] for call in fake.calls] == ["responses"]

    @pytest.mark.parametrize(
        ("dialect", "guarantee", "calls"),
        [
            ("json_schema", "schema_constrained", 1),
            ("tools", "tool_constrained", 2),
            ("json", "validated_json", 3),
        ],
        ids=["ollama-schema", "vllm-tools", "llamacpp-json"],
    )
    def test_returns_a_locally_validated_object(
        self, chat_endpoint, dialect, guarantee, calls
    ):
        fake, provider = chat_endpoint
        fake.chat_dialect = dialect

        result = provider.complete(REQUEST)

        assert result.value == {"caption": "A small boat"}
        assert (result.dialect, result.guarantee, result.repaired) == (
            dialect,
            guarantee,
            False,
        )
        assert len(fake.calls) == calls

    def test_reuses_a_probed_dialect(self, chat_endpoint):
        fake, provider = chat_endpoint
        fake.chat_dialect = "json"
        provider.complete(REQUEST)
        fake.calls.clear()

        result = provider.complete(REQUEST)

        assert result.dialect == "json"
        assert len(fake.calls) == 1

    def test_repairs_json_once(self, chat_endpoint):
        fake, provider = chat_endpoint
        fake.chat_dialect = "json"
        fake.chat_malformed_remaining = 1

        result = provider.complete(REQUEST)

        assert result.value == {"caption": "A small boat"}
        assert result.repaired is True
        assert len(fake.calls) == 4

    def test_rejects_a_failed_repair(self, chat_endpoint):
        fake, provider = chat_endpoint
        fake.chat_dialect = "json"
        fake.chat_malformed_remaining = 2

        with pytest.raises(EmbeddingError, match="chat_output_invalid"):
            provider.complete(REQUEST)

        assert len(fake.calls) == 4

    def test_rejects_unsupported_fields_locally(self, chat_endpoint):
        fake, provider = chat_endpoint
        fake.chat_result = {
            "caption": "A boat",
            "dangerous_extra": "ignored by endpoint schema",
        }

        with pytest.raises(EmbeddingError, match="chat_output_invalid"):
            provider.complete(REQUEST)

        assert len(fake.calls) == 1

    def test_never_changes_dialect_after_timeout(self, chat_endpoint):
        fake, provider = chat_endpoint
        fake.fault = "timeout"

        with pytest.raises(EmbeddingError, match="inference_timeout"):
            provider.complete(REQUEST, context=InferenceContext.bounded(0.3))

        assert len(fake.calls) == 1
        assert fake.calls[0]["body"]["response_format"]["type"] == "json_schema"

    def test_never_changes_dialect_after_server_failure(self, chat_endpoint):
        fake, provider = chat_endpoint
        fake.fault = "500"

        with pytest.raises(EmbeddingError, match="inference_endpoint_failed"):
            provider.complete(REQUEST)

        assert len(fake.calls) == 3
        assert [
            call["body"].get("response_format", {}).get("type") for call in fake.calls
        ] == ["json_schema"] * 3

    def test_rejects_external_schema_references_before_egress(self, chat_endpoint):
        fake, provider = chat_endpoint
        request = ChatInput(
            instruction="Describe.",
            text="boat",
            schema={
                "type": "object",
                "additionalProperties": False,
                "$ref": "http://test.invalid/schema",
            },
        )

        with pytest.raises(EmbeddingError, match="chat_schema_invalid"):
            provider.complete(request)

        assert fake.calls == []

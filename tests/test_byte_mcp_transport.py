import asyncio

import pytest

from bsap.byte_mcp_transport import (
    ByteMCPNvidiaTransport,
    StreamableHttpNvidiaQueryInvoker,
    _completed_response,
    _extract_model_text,
    _extract_tool_mapping,
    _query_id_from_start,
    _validate_async_nvidia_query_schema,
)
from bsap.model_transport import (
    ModelMessage,
    ModelRequest,
    ModelTransportError,
    ProviderFailureCategory,
)


class RecordingInvoker:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[dict[str, str]] = []

    def invoke(self, *, prompt: str, model: str, system_prompt: str) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "system_prompt": system_prompt,
            }
        )
        return self.result


class FailingInvoker:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, *, prompt: str, model: str, system_prompt: str) -> str:
        self.calls += 1
        raise ModelTransportError(
            ProviderFailureCategory.TIMEOUT,
            "Byte-MCP async NVIDIA request timed out",
        )


def request() -> ModelRequest:
    return ModelRequest(
        system_prompt="bounded system",
        messages=(
            ModelMessage(role="user", content='{"objective":"inspect"}'),
            ModelMessage(role="assistant", content='{"type":"tool_request"}'),
        ),
    )


def test_transport_identifies_provider_and_model() -> None:
    transport = ByteMCPNvidiaTransport(invoker=RecordingInvoker("{}"))
    assert transport.transport_name == "byte-mcp-nvidia-async"
    assert transport.model_name == "lightning"


def test_send_invokes_one_async_query_start_abstraction_with_exact_alias_and_system_prompt() -> None:
    invoker = RecordingInvoker('{"type":"final_report","report":{}}')
    transport = ByteMCPNvidiaTransport(invoker=invoker)

    response = transport.send(request())

    assert response.text == invoker.result
    assert len(invoker.calls) == 1
    assert invoker.calls[0]["model"] == "lightning"
    assert invoker.calls[0]["system_prompt"] == "bounded system"
    assert invoker.calls[0]["prompt"].startswith(
        "Continue this bounded BSAP conversation. Conversation JSON:\n"
    )
    assert (
        '[{"content":"{\\\"objective\\\":\\\"inspect\\\"}","role":"user"},'
        '{"content":"{\\\"type\\\":\\\"tool_request\\\"}","role":"assistant"}]'
        in invoker.calls[0]["prompt"]
    )


def test_transport_does_not_retry_normalized_invoker_failure() -> None:
    invoker = FailingInvoker()
    transport = ByteMCPNvidiaTransport(invoker=invoker)
    with pytest.raises(ModelTransportError) as exc_info:
        transport.send(request())
    assert exc_info.value.category is ProviderFailureCategory.TIMEOUT
    assert invoker.calls == 1


def start_schema(*, include_system_prompt: bool = True):
    properties = {
        "prompt": {"type": "string"},
        "model": {"type": "string"},
    }
    if include_system_prompt:
        properties["system_prompt"] = {"type": "string"}
    return {
        "name": "nvidia_query_start",
        "inputSchema": {
            "type": "object",
            "properties": properties,
        },
    }


def get_schema():
    return {
        "name": "nvidia_get_query",
        "inputSchema": {
            "type": "object",
            "properties": {"query_id": {"type": "string"}},
        },
    }


def test_expected_async_nvidia_query_schema_is_accepted() -> None:
    _validate_async_nvidia_query_schema([start_schema(), get_schema()])


def test_snake_case_input_schema_is_accepted_for_sdk_compatibility() -> None:
    start = start_schema()
    get = get_schema()
    start["input_schema"] = start.pop("inputSchema")
    get["input_schema"] = get.pop("inputSchema")
    _validate_async_nvidia_query_schema([start, get])


@pytest.mark.parametrize(
    "tools",
    [
        [],
        [{"name": "nvidia_query", "inputSchema": {"properties": {}}}],
        [start_schema(include_system_prompt=False), get_schema()],
        [start_schema()],
        [get_schema()],
        [start_schema(), start_schema(), get_schema()],
    ],
)
def test_async_schema_mismatch_fails_closed(tools) -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _validate_async_nvidia_query_schema(tools)
    assert exc_info.value.category is ProviderFailureCategory.CONTRACT_MISMATCH


def test_tool_mapping_prefers_structured_content() -> None:
    assert _extract_tool_mapping(
        {
            "isError": False,
            "structuredContent": {"query_id": "NVQ-000001", "status": "QUEUED"},
            "content": [],
        }
    ) == {"query_id": "NVQ-000001", "status": "QUEUED"}


def test_tool_mapping_accepts_single_json_text_block() -> None:
    assert _extract_tool_mapping(
        {
            "isError": False,
            "structuredContent": None,
            "content": [
                {
                    "type": "text",
                    "text": '{"query_id":"NVQ-000001","status":"RUNNING"}',
                }
            ],
        }
    ) == {"query_id": "NVQ-000001", "status": "RUNNING"}


def test_tool_error_is_normalized_without_exposing_raw_payload() -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _extract_tool_mapping(
            {
                "isError": True,
                "structuredContent": None,
                "content": [{"type": "text", "text": "SECRET-UPSTREAM-PAYLOAD"}],
            }
        )
    assert exc_info.value.category is ProviderFailureCategory.UNEXPECTED_PROVIDER_FAILURE
    assert "SECRET-UPSTREAM-PAYLOAD" not in str(exc_info.value)


def test_start_payload_requires_stable_query_identity() -> None:
    assert _query_id_from_start({"query_id": "NVQ-000123", "status": "QUEUED"}) == "NVQ-000123"
    with pytest.raises(ModelTransportError):
        _query_id_from_start({"query_id": "bad", "status": "QUEUED"})


def test_completed_async_query_returns_response() -> None:
    assert (
        _completed_response(
            {
                "query_id": "NVQ-000001",
                "status": "COMPLETED",
                "response": '{"type":"tool_request"}',
            },
            expected_query_id="NVQ-000001",
        )
        == '{"type":"tool_request"}'
    )


@pytest.mark.parametrize("status", ["PREPARED", "QUEUED", "RUNNING"])
def test_active_async_query_returns_none_without_provider_retry(status: str) -> None:
    assert (
        _completed_response(
            {
                "query_id": "NVQ-000001",
                "status": status,
                "provider_started": status == "RUNNING",
            },
            expected_query_id="NVQ-000001",
        )
        is None
    )


def test_failed_async_query_is_safely_classified() -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _completed_response(
            {
                "query_id": "NVQ-000001",
                "status": "FAILED",
                "provider_started": True,
                "nvidia_failure_kind": "PROVIDER_UNAVAILABLE",
            },
            expected_query_id="NVQ-000001",
        )
    assert exc_info.value.category is ProviderFailureCategory.UNAVAILABLE


def test_outcome_unknown_is_preserved() -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _completed_response(
            {
                "query_id": "NVQ-000001",
                "status": "OUTCOME_UNKNOWN",
                "provider_started": True,
            },
            expected_query_id="NVQ-000001",
        )
    assert exc_info.value.category is ProviderFailureCategory.OUTCOME_UNKNOWN


def test_legacy_model_text_helper_remains_strict() -> None:
    assert _extract_model_text(
        {
            "isError": False,
            "structuredContent": {"response": '{"type":"tool_request"}'},
            "content": [],
        }
    ) == '{"type":"tool_request"}'


def test_synchronous_invoker_rejects_nested_event_loop() -> None:
    invoker = StreamableHttpNvidiaQueryInvoker("http://127.0.0.1:8000/mcp")

    async def nested() -> None:
        with pytest.raises(ModelTransportError) as exc_info:
            invoker.invoke(prompt="p", model="lightning", system_prompt="s")
        assert exc_info.value.category is ProviderFailureCategory.TRANSPORT_FAILURE

    asyncio.run(nested())



def test_failed_async_query_with_unknown_attempt_preserves_ambiguity() -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _completed_response(
            {
                "query_id": "NVQ-000002",
                "status": "FAILED",
                "provider_started": True,
                "attempt_outcome": "OUTCOME_UNKNOWN",
                "transport_failure_kind": "ABSOLUTE_DEADLINE",
            },
            expected_query_id="NVQ-000002",
        )
    assert exc_info.value.category is ProviderFailureCategory.OUTCOME_UNKNOWN



def test_default_async_poll_budget_covers_provider_deadline_and_grace() -> None:
    invoker = StreamableHttpNvidiaQueryInvoker("http://127.0.0.1:8000/mcp")
    assert invoker._poll_timeout_seconds == 660.0

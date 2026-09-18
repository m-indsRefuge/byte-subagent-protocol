import asyncio

import pytest

from bsap.byte_mcp_transport import (
    ByteMCPNvidiaTransport,
    StreamableHttpNvidiaQueryInvoker,
    _extract_model_text,
    _validate_nvidia_query_schema,
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
            "Byte-MCP NVIDIA request timed out",
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
    assert transport.transport_name == "byte-mcp-nvidia"
    assert transport.model_name == "lightning"


def test_send_invokes_nvidia_query_once_with_exact_alias_and_system_prompt() -> None:
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


def tool_schema(*, include_system_prompt: bool = True):
    properties = {
        "prompt": {"type": "string"},
        "model": {"type": "string"},
    }
    if include_system_prompt:
        properties["system_prompt"] = {"type": "string"}
    return {
        "name": "nvidia_query",
        "inputSchema": {
            "type": "object",
            "properties": properties,
        },
    }


def test_expected_nvidia_query_schema_is_accepted() -> None:
    _validate_nvidia_query_schema([tool_schema()])


def test_snake_case_input_schema_is_accepted_for_sdk_compatibility() -> None:
    tool = tool_schema()
    tool["input_schema"] = tool.pop("inputSchema")
    _validate_nvidia_query_schema([tool])


@pytest.mark.parametrize(
    "tools",
    [
        [],
        [{"name": "search", "inputSchema": {"properties": {}}}],
        [tool_schema(include_system_prompt=False)],
        [tool_schema(), tool_schema()],
    ],
)
def test_schema_mismatch_fails_closed(tools) -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _validate_nvidia_query_schema(tools)
    assert exc_info.value.category is ProviderFailureCategory.CONTRACT_MISMATCH


def test_structured_response_string_is_extracted() -> None:
    assert _extract_model_text(
        {
            "isError": False,
            "structuredContent": {"response": '{"type":"tool_request"}'},
            "content": [],
        }
    ) == '{"type":"tool_request"}'


def test_single_text_content_string_is_extracted() -> None:
    assert _extract_model_text(
        {
            "isError": False,
            "structuredContent": None,
            "content": [{"type": "text", "text": '{"type":"final_report"}'}],
        }
    ) == '{"type":"final_report"}'


def test_multiple_candidate_strings_are_rejected() -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _extract_model_text(
            {
                "isError": False,
                "structuredContent": {"response": "a", "text": "b"},
                "content": [],
            }
        )
    assert exc_info.value.category is ProviderFailureCategory.MALFORMED_RESPONSE


def test_error_result_is_normalized_without_exposing_raw_payload() -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _extract_model_text(
            {
                "isError": True,
                "structuredContent": None,
                "content": [{"type": "text", "text": "SECRET-UPSTREAM-PAYLOAD"}],
            }
        )
    assert exc_info.value.category is ProviderFailureCategory.UNEXPECTED_PROVIDER_FAILURE
    assert "SECRET-UPSTREAM-PAYLOAD" not in str(exc_info.value)


def test_missing_response_string_is_malformed() -> None:
    with pytest.raises(ModelTransportError) as exc_info:
        _extract_model_text({"isError": False, "structuredContent": {}, "content": []})
    assert exc_info.value.category is ProviderFailureCategory.MALFORMED_RESPONSE


def test_synchronous_invoker_rejects_nested_event_loop() -> None:
    invoker = StreamableHttpNvidiaQueryInvoker("http://127.0.0.1:8000/mcp")

    async def nested() -> None:
        with pytest.raises(ModelTransportError) as exc_info:
            invoker.invoke(prompt="p", model="lightning", system_prompt="s")
        assert exc_info.value.category is ProviderFailureCategory.TRANSPORT_FAILURE

    asyncio.run(nested())

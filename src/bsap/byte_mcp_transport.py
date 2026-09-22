from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from bsap.canonical import canonical_json
from bsap.model_transport import (
    ModelRequest,
    ModelResponse,
    ModelTransportError,
    ProviderFailureCategory,
)

_QUERY_ID = re.compile(r"NVQ-[0-9]{6}\Z")
_ACTIVE_QUERY_STATUSES = frozenset({"PREPARED", "QUEUED", "RUNNING"})
_TERMINAL_QUERY_STATUSES = frozenset({"COMPLETED", "FAILED", "OUTCOME_UNKNOWN"})
_ALL_QUERY_STATUSES = _ACTIVE_QUERY_STATUSES | _TERMINAL_QUERY_STATUSES


class NvidiaQueryInvoker(Protocol):
    def invoke(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str,
    ) -> str: ...


def _field(value: object, *names: str) -> object | None:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _tool_schema(tools: Sequence[object], name: str) -> Mapping[str, object]:
    matches = [tool for tool in tools if _field(tool, "name") == name]
    if len(matches) != 1:
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP async NVIDIA query schema does not match EXEC-02",
        )
    schema = _field(matches[0], "inputSchema", "input_schema")
    if not isinstance(schema, Mapping):
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP async NVIDIA query schema does not match EXEC-02",
        )
    return schema


def _schema_properties(schema: Mapping[str, object]) -> Mapping[str, object]:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP async NVIDIA query schema does not match EXEC-02",
        )
    return properties


def _validate_async_nvidia_query_schema(tools: Sequence[object]) -> None:
    start_properties = _schema_properties(_tool_schema(tools, "nvidia_query_start"))
    get_properties = _schema_properties(_tool_schema(tools, "nvidia_get_query"))

    if not {"prompt", "model", "system_prompt"}.issubset(start_properties):
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP async NVIDIA query schema does not match EXEC-02",
        )
    if "query_id" not in get_properties:
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP async NVIDIA query schema does not match EXEC-02",
        )


def _validate_nvidia_query_schema(tools: Sequence[object]) -> None:
    """Compatibility alias for the EXEC-02 async schema validator."""
    _validate_async_nvidia_query_schema(tools)


def _extract_tool_mapping(result: object) -> dict[str, object]:
    if bool(_field(result, "isError", "is_error")):
        raise ModelTransportError(
            ProviderFailureCategory.UNEXPECTED_PROVIDER_FAILURE,
            "Byte-MCP async NVIDIA query tool returned an error",
        )

    structured = _field(result, "structuredContent", "structured_content")
    if isinstance(structured, Mapping):
        return dict(structured)

    content = _field(result, "content")
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        texts = [
            text
            for block in content
            if _field(block, "type") == "text"
            and isinstance((text := _field(block, "text")), str)
        ]
        if len(texts) == 1:
            try:
                payload = json.loads(texts[0])
            except json.JSONDecodeError as exc:
                raise ModelTransportError(
                    ProviderFailureCategory.MALFORMED_RESPONSE,
                    "Byte-MCP async NVIDIA query returned invalid JSON",
                ) from exc
            if isinstance(payload, dict):
                return payload

    raise ModelTransportError(
        ProviderFailureCategory.MALFORMED_RESPONSE,
        "Byte-MCP async NVIDIA query returned an invalid result",
    )


def _extract_model_text(result: object) -> str:
    """Legacy helper retained for deterministic compatibility tests."""
    payload = _extract_tool_mapping(result)
    candidates = [
        value
        for key in ("response", "result", "text", "content")
        if isinstance((value := payload.get(key)), str)
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise ModelTransportError(
        ProviderFailureCategory.MALFORMED_RESPONSE,
        "Byte-MCP NVIDIA result did not contain one response string",
    )


def _query_id_from_start(payload: Mapping[str, object]) -> str:
    query_id = payload.get("query_id")
    status = payload.get("status")
    if (
        not isinstance(query_id, str)
        or _QUERY_ID.fullmatch(query_id) is None
        or not isinstance(status, str)
        or status not in _ALL_QUERY_STATUSES
    ):
        raise ModelTransportError(
            ProviderFailureCategory.MALFORMED_RESPONSE,
            "Byte-MCP async NVIDIA query start result is invalid",
        )
    return query_id


def _failure_category(payload: Mapping[str, object]) -> ProviderFailureCategory:
    error_code = payload.get("error_code")
    nvidia_kind = payload.get("nvidia_failure_kind")
    transport_kind = payload.get("transport_failure_kind")

    if isinstance(transport_kind, str) and transport_kind:
        return ProviderFailureCategory.TRANSPORT_FAILURE
    if nvidia_kind in {"PROVIDER_UNAVAILABLE", "MODEL_OR_ENDPOINT_UNAVAILABLE"}:
        return ProviderFailureCategory.UNAVAILABLE
    if nvidia_kind in {
        "AUTHENTICATION",
        "PERMISSION",
        "REQUEST",
        "REQUEST_TOO_LARGE",
        "RATE_LIMIT",
    }:
        return ProviderFailureCategory.REJECTED_REQUEST
    if error_code == "CREDENTIAL_UNAVAILABLE":
        return ProviderFailureCategory.UNAVAILABLE
    return ProviderFailureCategory.UNEXPECTED_PROVIDER_FAILURE


def _completed_response(
    payload: Mapping[str, object],
    *,
    expected_query_id: str,
) -> str | None:
    query_id = payload.get("query_id")
    status = payload.get("status")
    if query_id != expected_query_id or not isinstance(status, str) or status not in _ALL_QUERY_STATUSES:
        raise ModelTransportError(
            ProviderFailureCategory.MALFORMED_RESPONSE,
            "Byte-MCP async NVIDIA query status result is invalid",
        )

    if status in _ACTIVE_QUERY_STATUSES:
        return None
    if status == "OUTCOME_UNKNOWN" or (
        status == "FAILED" and payload.get("attempt_outcome") == "OUTCOME_UNKNOWN"
    ):
        raise ModelTransportError(
            ProviderFailureCategory.OUTCOME_UNKNOWN,
            "Byte-MCP async NVIDIA query outcome is unknown",
        )
    if status == "FAILED":
        raise ModelTransportError(
            _failure_category(payload),
            "Byte-MCP async NVIDIA query failed",
        )

    response = payload.get("response")
    if not isinstance(response, str) or not response:
        raise ModelTransportError(
            ProviderFailureCategory.MALFORMED_RESPONSE,
            "Byte-MCP async NVIDIA query completed without a response",
        )
    return response


class ByteMCPNvidiaTransport:
    def __init__(
        self,
        *,
        invoker: NvidiaQueryInvoker,
        model_alias: str = "lightning",
    ) -> None:
        self._invoker = invoker
        self._model_alias = model_alias

    @property
    def transport_name(self) -> str:
        return "byte-mcp-nvidia-async"

    @property
    def model_name(self) -> str:
        return self._model_alias

    def send(self, request: ModelRequest) -> ModelResponse:
        conversation = canonical_json(request.messages)
        prompt = (
            "Continue this bounded BSAP conversation. Conversation JSON:\n"
            + conversation
        )
        text = self._invoker.invoke(
            prompt=prompt,
            model=self._model_alias,
            system_prompt=request.system_prompt,
        )
        return ModelResponse(text=text)


class StreamableHttpNvidiaQueryInvoker:
    def __init__(
        self,
        mcp_url: str,
        *,
        poll_interval_seconds: float = 2.0,
        poll_timeout_seconds: float = 420.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if poll_timeout_seconds <= 0:
            raise ValueError("poll_timeout_seconds must be positive")
        self._mcp_url = mcp_url
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_timeout_seconds = poll_timeout_seconds

    def probe_schema(self) -> None:
        self._ensure_no_running_loop()
        self._run(self._probe_schema_async())

    def invoke(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str,
    ) -> str:
        self._ensure_no_running_loop()
        return self._run(
            self._invoke_async(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
            )
        )

    @staticmethod
    def _ensure_no_running_loop() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise ModelTransportError(
            ProviderFailureCategory.TRANSPORT_FAILURE,
            "Byte-MCP transport cannot run inside an existing event loop",
        )

    def _run(self, awaitable):
        try:
            return asyncio.run(awaitable)
        except ModelTransportError:
            raise
        except TimeoutError as exc:
            raise ModelTransportError(
                ProviderFailureCategory.TIMEOUT,
                "Byte-MCP async NVIDIA request timed out",
            ) from exc
        except Exception as exc:
            raise ModelTransportError(
                ProviderFailureCategory.TRANSPORT_FAILURE,
                "Byte-MCP async NVIDIA transport failed",
            ) from exc

    @staticmethod
    def _mcp_imports():
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise ModelTransportError(
                ProviderFailureCategory.TRANSPORT_FAILURE,
                "MCP client dependency is unavailable",
            ) from exc
        return ClientSession, streamable_http_client

    async def _probe_schema_async(self) -> None:
        ClientSession, streamable_http_client = self._mcp_imports()
        async with streamable_http_client(self._mcp_url) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                try:
                    listed = await session.list_tools()
                except Exception as exc:
                    raise ModelTransportError(
                        ProviderFailureCategory.TRANSPORT_FAILURE,
                        "Byte-MCP async NVIDIA schema listing failed",
                        stage="schema",
                    ) from exc
                tools = _field(listed, "tools")
                if not isinstance(tools, Sequence):
                    raise ModelTransportError(
                        ProviderFailureCategory.CONTRACT_MISMATCH,
                        "Byte-MCP did not return a valid tool list",
                    )
                _validate_async_nvidia_query_schema(tools)

    async def _invoke_async(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str,
    ) -> str:
        ClientSession, streamable_http_client = self._mcp_imports()
        async with streamable_http_client(self._mcp_url) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                try:
                    listed = await session.list_tools()
                except Exception as exc:
                    raise ModelTransportError(
                        ProviderFailureCategory.TRANSPORT_FAILURE,
                        "Byte-MCP async NVIDIA schema listing failed",
                        stage="schema",
                    ) from exc
                tools = _field(listed, "tools")
                if not isinstance(tools, Sequence):
                    raise ModelTransportError(
                        ProviderFailureCategory.CONTRACT_MISMATCH,
                        "Byte-MCP did not return a valid tool list",
                    )
                _validate_async_nvidia_query_schema(tools)

                try:
                    started = await session.call_tool(
                        "nvidia_query_start",
                        arguments={
                            "prompt": prompt,
                            "model": model,
                            "system_prompt": system_prompt,
                        },
                    )
                except Exception as exc:
                    raise ModelTransportError(
                        ProviderFailureCategory.OUTCOME_UNKNOWN,
                        "Byte-MCP async NVIDIA query start outcome is unknown",
                        stage="start",
                    ) from exc
                start_payload = _extract_tool_mapping(started)
                query_id = _query_id_from_start(start_payload)

                loop = asyncio.get_running_loop()
                deadline = loop.time() + self._poll_timeout_seconds
                while True:
                    try:
                        fetched = await session.call_tool(
                            "nvidia_get_query",
                            arguments={"query_id": query_id},
                        )
                    except Exception as exc:
                        raise ModelTransportError(
                            ProviderFailureCategory.OUTCOME_UNKNOWN,
                            "Byte-MCP async NVIDIA query polling outcome is unknown",
                            stage="poll",
                        ) from exc
                    payload = _extract_tool_mapping(fetched)
                    response = _completed_response(
                        payload,
                        expected_query_id=query_id,
                    )
                    if response is not None:
                        return response

                    if loop.time() >= deadline:
                        if payload.get("provider_started") is True:
                            raise ModelTransportError(
                                ProviderFailureCategory.OUTCOME_UNKNOWN,
                                "Byte-MCP async NVIDIA query exceeded the polling deadline",
                            )
                        raise ModelTransportError(
                            ProviderFailureCategory.TIMEOUT,
                            "Byte-MCP async NVIDIA query did not start before the polling deadline",
                        )
                    await asyncio.sleep(self._poll_interval_seconds)

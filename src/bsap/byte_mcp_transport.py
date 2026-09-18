from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Protocol

from bsap.canonical import canonical_json
from bsap.model_transport import (
    ModelRequest,
    ModelResponse,
    ModelTransportError,
    ProviderFailureCategory,
)


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


def _validate_nvidia_query_schema(tools: Sequence[object]) -> None:
    matches = [tool for tool in tools if _field(tool, "name") == "nvidia_query"]
    if len(matches) != 1:
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP nvidia_query schema does not match EXEC-02",
        )

    schema = _field(matches[0], "inputSchema", "input_schema")
    if not isinstance(schema, Mapping):
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP nvidia_query schema does not match EXEC-02",
        )
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP nvidia_query schema does not match EXEC-02",
        )

    required_properties = {"prompt", "model", "system_prompt"}
    if not required_properties.issubset(properties):
        raise ModelTransportError(
            ProviderFailureCategory.CONTRACT_MISMATCH,
            "Byte-MCP nvidia_query schema does not match EXEC-02",
        )

    model_schema = properties["model"]
    if isinstance(model_schema, Mapping):
        model_type = model_schema.get("type")
        model_enum = model_schema.get("enum")
        string_capable = model_type in (None, "string") or (
            isinstance(model_enum, list)
            and bool(model_enum)
            and all(isinstance(item, str) for item in model_enum)
        )
        if not string_capable:
            raise ModelTransportError(
                ProviderFailureCategory.CONTRACT_MISMATCH,
                "Byte-MCP nvidia_query schema does not match EXEC-02",
            )


def _extract_model_text(result: object) -> str:
    is_error = bool(_field(result, "isError", "is_error"))
    if is_error:
        raise ModelTransportError(
            ProviderFailureCategory.UNEXPECTED_PROVIDER_FAILURE,
            "Byte-MCP nvidia_query returned an error",
        )

    structured = _field(result, "structuredContent", "structured_content")
    if isinstance(structured, Mapping):
        candidates = [
            value
            for key in ("response", "result", "text", "content")
            if isinstance((value := structured.get(key)), str)
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ModelTransportError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "Byte-MCP nvidia_query returned an ambiguous response",
            )

    content = _field(result, "content")
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        candidates: list[str] = []
        for block in content:
            block_type = _field(block, "type")
            text = _field(block, "text")
            if block_type == "text" and isinstance(text, str):
                candidates.append(text)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ModelTransportError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "Byte-MCP nvidia_query returned multiple text responses",
            )

    raise ModelTransportError(
        ProviderFailureCategory.MALFORMED_RESPONSE,
        "Byte-MCP nvidia_query did not return one model response string",
    )


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
        return "byte-mcp-nvidia"

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
    def __init__(self, mcp_url: str) -> None:
        self._mcp_url = mcp_url

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
                "Byte-MCP NVIDIA request timed out",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - normalize provider SDK failures
            raise ModelTransportError(
                ProviderFailureCategory.TRANSPORT_FAILURE,
                "Byte-MCP NVIDIA transport failed",
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
                listed = await session.list_tools()
                tools = _field(listed, "tools")
                if not isinstance(tools, Sequence):
                    raise ModelTransportError(
                        ProviderFailureCategory.CONTRACT_MISMATCH,
                        "Byte-MCP did not return a valid tool list",
                    )
                _validate_nvidia_query_schema(tools)

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
                listed = await session.list_tools()
                tools = _field(listed, "tools")
                if not isinstance(tools, Sequence):
                    raise ModelTransportError(
                        ProviderFailureCategory.CONTRACT_MISMATCH,
                        "Byte-MCP did not return a valid tool list",
                    )
                _validate_nvidia_query_schema(tools)
                result = await session.call_tool(
                    "nvidia_query",
                    arguments={
                        "prompt": prompt,
                        "model": model,
                        "system_prompt": system_prompt,
                    },
                )
                return _extract_model_text(result)

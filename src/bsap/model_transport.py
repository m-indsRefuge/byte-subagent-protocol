from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ProviderFailureCategory(StrEnum):
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    REJECTED_REQUEST = "rejected_request"
    MALFORMED_RESPONSE = "malformed_response"
    TRANSPORT_FAILURE = "transport_failure"
    UNEXPECTED_PROVIDER_FAILURE = "unexpected_provider_failure"
    CONTRACT_MISMATCH = "contract_mismatch"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ModelRequest:
    system_prompt: str
    messages: tuple[ModelMessage, ...]


@dataclass(frozen=True, slots=True)
class ModelResponse:
    text: str


class ModelTransportError(RuntimeError):
    def __init__(
        self,
        category: ProviderFailureCategory,
        safe_message: str,
    ) -> None:
        super().__init__(safe_message)
        self.category = category


class ModelTransport(Protocol):
    @property
    def transport_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def send(self, request: ModelRequest) -> ModelResponse: ...

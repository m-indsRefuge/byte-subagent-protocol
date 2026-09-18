from dataclasses import FrozenInstanceError

import pytest

from bsap.model_transport import (
    ModelMessage,
    ModelRequest,
    ModelTransportError,
    ProviderFailureCategory,
)
from bsap.models import ExecutorInfo


def test_model_request_is_immutable() -> None:
    request = ModelRequest(
        system_prompt="system",
        messages=(ModelMessage(role="user", content="task"),),
    )
    with pytest.raises(FrozenInstanceError):
        request.system_prompt = "changed"  # type: ignore[misc]


def test_transport_error_exposes_safe_category_without_raw_provider_payload() -> None:
    error = ModelTransportError(
        ProviderFailureCategory.TIMEOUT,
        "model transport timed out",
    )
    assert error.category is ProviderFailureCategory.TIMEOUT
    assert str(error) == "model transport timed out"


def test_executor_info_can_bind_transport_and_model() -> None:
    info = ExecutorInfo(
        type="model",
        version="0.2",
        transport="byte-mcp-nvidia",
        model="lightning",
    )
    assert info.transport == "byte-mcp-nvidia"
    assert info.model == "lightning"

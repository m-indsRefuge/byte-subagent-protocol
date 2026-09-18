import json
from datetime import UTC, datetime

import pytest

from bsap.lifecycle import EventLog
from bsap.model_executor import ModelExecutor
from bsap.model_protocol import ModelProtocolError
from bsap.model_transport import (
    ModelResponse,
    ModelTransportError,
    ProviderFailureCategory,
)
from bsap.models import (
    Budget,
    CompletionContract,
    ContextManifest,
    DelegationReason,
    PermissionSet,
    PreparedRequest,
)
from bsap.sandbox import (
    BudgetCounter,
    BudgetExceeded,
    InMemoryWorkspace,
    PermissionDenied,
    ToolDispatcher,
)


def fixed_clock() -> datetime:
    return datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def prepared(
    *,
    budget: Budget | None = None,
    permissions: PermissionSet | None = None,
) -> PreparedRequest:
    if budget is None:
        budget = Budget(max_steps=6, max_tool_calls=4)
    if permissions is None:
        permissions = PermissionSet(filesystem_read=True, tests_run=True)
    return PreparedRequest(
        agent_id="BSA-MODEL",
        parent_id="BYTE",
        role="investigator",
        objective="diagnose timeout conversion",
        delegation_reason=DelegationReason(
            trigger="verification",
            rationale="independent evidence",
            expected_value="root cause",
        ),
        context_manifest=ContextManifest(
            files=("settings.py", "client.py"),
            observations=("timeout=5000",),
            constraints=("read-only",),
        ),
        permissions=permissions,
        budget=budget,
        completion_contract=CompletionContract(
            require=("findings", "evidence", "recommended_next_action")
        ),
        request_sha256="a" * 64,
        context_manifest_sha256="b" * 64,
        policy_sha256="c" * 64,
    )


def tools_for(request: PreparedRequest) -> tuple[ToolDispatcher, EventLog]:
    log = EventLog(request.agent_id, clock=fixed_clock)
    workspace = InMemoryWorkspace(
        files={
            "settings.py": 'request_timeout_ms = "5000"',
            "client.py": "timeout = settings.request_timeout_seconds",
        },
        allowed_files=request.context_manifest.files,
        test_results={
            "timeout-conversion": {
                "name": "timeout-conversion",
                "passed": False,
                "exit_code": 1,
                "stdout": "expected 5 got 5000",
                "stderr": "",
                "timed_out": False,
            }
        },
    )
    dispatcher = ToolDispatcher(
        workspace=workspace,
        permissions=request.permissions,
        budget_counter=BudgetCounter(request.budget),
        emit=log.emit,
    )
    return dispatcher, log


def final_report() -> str:
    return json.dumps(
        {
            "type": "final_report",
            "report": {
                "status": "completed",
                "findings": [{"id": "F-1", "claim": "missing conversion"}],
                "evidence": [
                    {
                        "finding_id": "F-1",
                        "source": "settings.py",
                        "observation": "milliseconds copied directly",
                    }
                ],
                "alternative_hypotheses": [],
                "uncertainties": [],
                "recommended_next_action": ["convert at loader boundary"],
            },
        },
        separators=(",", ":"),
    )


class FakeModelTransport:
    def __init__(self, responses: tuple[str, ...]) -> None:
        self._responses = iter(responses)
        self.requests = []

    @property
    def transport_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fixture-model"

    def send(self, request):
        self.requests.append(request)
        return ModelResponse(next(self._responses))


class FailingTransport(FakeModelTransport):
    def __init__(self) -> None:
        super().__init__(())
        self.calls = 0

    def send(self, request):
        self.calls += 1
        raise ModelTransportError(
            ProviderFailureCategory.TIMEOUT,
            "model transport timed out",
        )


def test_final_report_on_first_turn_uses_one_step_and_no_tools() -> None:
    request = prepared()
    tools, log = tools_for(request)
    transport = FakeModelTransport((final_report(),))

    report = ModelExecutor(transport=transport).execute(request, tools, log.emit)

    assert report.findings[0].id == "F-1"
    assert len(transport.requests) == 1
    kinds = tuple(event.kind for event in log.events)
    assert kinds == (
        "model.requested",
        "model.completed",
        "report.started",
        "report.completed",
    )


def test_search_read_then_report_forms_one_conversation() -> None:
    responses = (
        '{"type":"tool_request","tool":"repository.search","arguments":{"query":"timeout"}}',
        '{"type":"tool_request","tool":"repository.read","arguments":{"path":"settings.py"}}',
        final_report(),
    )
    request = prepared()
    tools, log = tools_for(request)
    transport = FakeModelTransport(responses)

    report = ModelExecutor(transport=transport).execute(request, tools, log.emit)

    assert report.findings[0].claim == "missing conversion"
    assert len(transport.requests) == 3
    second_messages = transport.requests[1].messages
    assert second_messages[-2].role == "assistant"
    assert '"tool":"repository.search"' in second_messages[-2].content
    assert second_messages[-1].role == "user"
    assert '"type":"tool_result"' in second_messages[-1].content
    assert '"tool":"repository.search"' in second_messages[-1].content
    kinds = tuple(event.kind for event in log.events)
    assert kinds.count("tool.completed") == 2


def test_test_result_is_appended_to_next_model_turn() -> None:
    responses = (
        '{"type":"tool_request","tool":"tests.run","arguments":{"name":"timeout-conversion"}}',
        final_report(),
    )
    request = prepared()
    tools, log = tools_for(request)
    transport = FakeModelTransport(responses)

    ModelExecutor(transport=transport).execute(request, tools, log.emit)

    assert len(transport.requests) == 2
    assert '"passed":false' in transport.requests[1].messages[-1].content
    assert '"name":"timeout-conversion"' in transport.requests[1].messages[-1].content


def test_step_budget_blocks_second_model_turn_before_transport_send() -> None:
    request = prepared(budget=Budget(max_steps=1, max_tool_calls=4))
    tools, log = tools_for(request)
    transport = FakeModelTransport(
        (
            '{"type":"tool_request","tool":"repository.search","arguments":{"query":"timeout"}}',
            final_report(),
        )
    )

    with pytest.raises(BudgetExceeded):
        ModelExecutor(transport=transport).execute(request, tools, log.emit)

    assert len(transport.requests) == 1
    assert log.events[-1].kind == "budget.exhausted"


def test_malformed_json_emits_protocol_failure_once_and_does_not_retry() -> None:
    request = prepared()
    tools, log = tools_for(request)
    transport = FakeModelTransport(("not-json", final_report()))

    with pytest.raises(ModelProtocolError):
        ModelExecutor(transport=transport).execute(request, tools, log.emit)

    assert len(transport.requests) == 1
    failures = [event for event in log.events if event.kind == "protocol.failed"]
    assert len(failures) == 1
    assert failures[0].payload["code"] == "invalid_json"


def test_provider_failure_emits_once_and_does_not_retry() -> None:
    request = prepared()
    tools, log = tools_for(request)
    transport = FailingTransport()

    with pytest.raises(ModelTransportError):
        ModelExecutor(transport=transport).execute(request, tools, log.emit)

    assert transport.calls == 1
    failures = [event for event in log.events if event.kind == "provider.failed"]
    assert len(failures) == 1
    assert failures[0].payload["category"] == "timeout"


def test_ungranted_test_request_is_denied_by_tool_dispatcher() -> None:
    request = prepared(permissions=PermissionSet(filesystem_read=True, tests_run=False))
    tools, log = tools_for(request)
    transport = FakeModelTransport(
        ('{"type":"tool_request","tool":"tests.run","arguments":{"name":"timeout-conversion"}}',)
    )

    with pytest.raises(PermissionDenied):
        ModelExecutor(transport=transport).execute(request, tools, log.emit)

    assert log.events[-1].kind == "permission.denied"


def test_executor_info_reports_transport_and_model() -> None:
    transport = FakeModelTransport((final_report(),))
    info = ModelExecutor(transport=transport).info
    assert info.type == "model"
    assert info.version == "0.2"
    assert info.transport == "fake"
    assert info.model == "fixture-model"

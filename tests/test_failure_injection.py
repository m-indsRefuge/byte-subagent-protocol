from datetime import UTC, datetime

from bsap.executor import ExecutionCancelled, ScriptedDeterministicExecutor
from bsap.lifecycle import EventLog, EventStoreFailure
from bsap.manager import SubAgentManager
from bsap.model_protocol import ModelProtocolError
from bsap.model_transport import ModelTransportError, ProviderFailureCategory
from bsap.models import (
    BsapReport,
    BsapRequest,
    Budget,
    CompletionContract,
    ContextManifest,
    DelegationReason,
    PermissionSet,
    TerminalOutcome,
    ToolCall,
)
from bsap.sandbox import InMemoryWorkspace, OutcomeUnknownError, ToolTimeout


def fixed_clock() -> datetime:
    return datetime(2026, 9, 17, 21, 30, tzinfo=UTC)


def make_manager(*, event_log_factory=None) -> SubAgentManager:
    return SubAgentManager(
        id_factory=lambda: "BSA-FAIL",
        clock=fixed_clock,
        event_log_factory=event_log_factory,
    )


def request() -> BsapRequest:
    return BsapRequest(
        role="investigator",
        objective="failure injection",
        delegation_reason=DelegationReason("verification", "failure boundary", "classification"),
        context_requirements=("fixture",),
        requested_capabilities=("repository.read", "tests.run"),
        completion_contract=CompletionContract(require=("findings", "evidence")),
    )


def prepare(manager: SubAgentManager, budget: Budget | None = None):
    return manager.prepare(
        request(),
        context_manifest=ContextManifest(files=("a.py",)),
        permissions=PermissionSet(filesystem_read=True, tests_run=True),
        budget=budget or Budget(10, 10),
    )


class CrashingExecutor:
    @property
    def info(self):
        from bsap.models import ExecutorInfo
        return ExecutorInfo(type="deterministic", version="crash")

    def execute(self, prepared, tools, emit):
        raise RuntimeError("deterministic crash")


class CancellingExecutor(CrashingExecutor):
    def execute(self, prepared, tools, emit):
        raise ExecutionCancelled("cancelled")


class ProviderFailingExecutor(CrashingExecutor):
    def execute(self, prepared, tools, emit):
        raise ModelTransportError(
            ProviderFailureCategory.TIMEOUT,
            "safe timeout classification",
        )


class ProviderOutcomeUnknownExecutor(CrashingExecutor):
    def execute(self, prepared, tools, emit):
        raise ModelTransportError(
            ProviderFailureCategory.OUTCOME_UNKNOWN,
            "safe provider ambiguity",
        )


class ProtocolFailingExecutor(CrashingExecutor):
    def execute(self, prepared, tools, emit):
        raise ModelProtocolError("invalid_json", "safe protocol classification")


class TimeoutWorkspace(InMemoryWorkspace):
    def run_test(self, name: str):
        raise ToolTimeout("deterministic timeout")


class UnknownWorkspace(InMemoryWorkspace):
    def read(self, path: str):
        raise OutcomeUnknownError("lost confirmation after tool started")


class FailingEventLog(EventLog):
    def emit(self, kind, payload):
        if kind == "tool.requested":
            raise EventStoreFailure("event store unavailable")
        return super().emit(kind, payload)


def empty_workspace(cls=InMemoryWorkspace):
    return cls(files={"a.py": "x = 1"}, allowed_files=("a.py",), test_results={"unit": {"exit_code": 1}})


def invalid_report(agent_id: str) -> BsapReport:
    return BsapReport(
        agent_id=agent_id,
        status="completed",
        findings=(),
        evidence=(),
        alternative_hypotheses=(),
        uncertainties=(),
        recommended_next_action=(),
    )


def test_executor_crash_before_tools_is_failed() -> None:
    manager = make_manager()
    result = manager.run(prepare(manager), CrashingExecutor(), empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.FAILED


def test_read_only_tool_timeout_is_failed() -> None:
    manager = make_manager()
    executor = ScriptedDeterministicExecutor(
        actions=(ToolCall("tests.run", {"name": "unit"}),),
        report_builder=lambda results: invalid_report("BSA-FAIL"),
    )
    result = manager.run(prepare(manager), executor, empty_workspace(TimeoutWorkspace))
    assert result.terminal_outcome is TerminalOutcome.FAILED


def test_budget_exhaustion_blocks_execution_and_is_failed() -> None:
    manager = make_manager()
    executor = ScriptedDeterministicExecutor(
        actions=(ToolCall("repository.read", {"path": "a.py"}),),
        report_builder=lambda results: invalid_report("BSA-FAIL"),
    )
    result = manager.run(prepare(manager, Budget(10, 0)), executor, empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.FAILED
    assert all(event.kind != "tool.started" for event in result.events)


def test_malformed_report_cannot_complete() -> None:
    manager = make_manager()
    executor = ScriptedDeterministicExecutor(actions=(), report_builder=lambda results: invalid_report("BSA-FAIL"))
    result = manager.run(prepare(manager), executor, empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.FAILED
    assert result.report is None


def test_cancellation_is_distinct_terminal_outcome() -> None:
    manager = make_manager()
    result = manager.run(prepare(manager), CancellingExecutor(), empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.CANCELLED


def test_unknown_effect_after_tool_started_is_outcome_unknown() -> None:
    manager = make_manager()
    executor = ScriptedDeterministicExecutor(
        actions=(ToolCall("repository.read", {"path": "a.py"}),),
        report_builder=lambda results: invalid_report("BSA-FAIL"),
    )
    result = manager.run(prepare(manager), executor, empty_workspace(UnknownWorkspace))
    assert result.terminal_outcome is TerminalOutcome.OUTCOME_UNKNOWN
    assert result.receipt.terminal_state is TerminalOutcome.OUTCOME_UNKNOWN


def test_event_store_failure_after_start_is_outcome_unknown() -> None:
    manager = make_manager(event_log_factory=lambda agent_id, clock: FailingEventLog(agent_id, clock))
    executor = ScriptedDeterministicExecutor(
        actions=(ToolCall("repository.read", {"path": "a.py"}),),
        report_builder=lambda results: invalid_report("BSA-FAIL"),
    )
    result = manager.run(prepare(manager), executor, empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.OUTCOME_UNKNOWN


def test_parent_can_cancel_prepared_child_and_release_slot() -> None:
    manager = SubAgentManager(id_factory=iter(("BSA-CANCEL", "BSA-NEXT")).__next__, clock=fixed_clock)
    prepared = prepare(manager)
    result = manager.cancel(prepared.agent_id)
    assert result.terminal_outcome is TerminalOutcome.CANCELLED
    assert result.final_state.value == "TERMINATED"
    next_prepared = manager.prepare(
        request(),
        context_manifest=ContextManifest(files=("a.py",)),
        permissions=PermissionSet(filesystem_read=True),
        budget=Budget(10, 10),
    )
    assert next_prepared.agent_id == "BSA-NEXT"


def test_context_denial_is_known_failure_not_unknown_outcome() -> None:
    manager = make_manager()
    executor = ScriptedDeterministicExecutor(
        actions=(ToolCall("repository.read", {"path": "secret.py"}),),
        report_builder=lambda results: invalid_report("BSA-FAIL"),
    )
    result = manager.run(prepare(manager), executor, empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.FAILED



def test_provider_failure_has_explicit_safe_classification() -> None:
    manager = make_manager()
    result = manager.run(prepare(manager), ProviderFailingExecutor(), empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.FAILED
    failed_event = next(event for event in result.events if event.kind == "agent.failed")
    assert failed_event.payload == {
        "classification": "FAILED",
        "reason": "provider_failure",
        "category": "timeout",
    }
    assert "safe timeout classification" not in repr(failed_event.payload)


def test_protocol_failure_has_explicit_safe_classification() -> None:
    manager = make_manager()
    result = manager.run(prepare(manager), ProtocolFailingExecutor(), empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.FAILED
    failed_event = next(event for event in result.events if event.kind == "agent.failed")
    assert failed_event.payload == {
        "classification": "FAILED",
        "reason": "protocol_failure",
        "code": "invalid_json",
    }
    assert "safe protocol classification" not in repr(failed_event.payload)


def test_model_failure_releases_active_child_slot() -> None:
    ids = iter(("BSA-FIRST", "BSA-NEXT"))
    manager = SubAgentManager(id_factory=ids.__next__, clock=fixed_clock)
    first = manager.prepare(
        request(),
        context_manifest=ContextManifest(files=("a.py",)),
        permissions=PermissionSet(filesystem_read=True, tests_run=True),
        budget=Budget(10, 10),
    )
    result = manager.run(first, ProviderFailingExecutor(), empty_workspace())
    assert result.terminal_outcome is TerminalOutcome.FAILED
    next_prepared = manager.prepare(
        request(),
        context_manifest=ContextManifest(files=("a.py",)),
        permissions=PermissionSet(filesystem_read=True, tests_run=True),
        budget=Budget(10, 10),
    )
    assert next_prepared.agent_id == "BSA-NEXT"



def test_provider_outcome_unknown_preserves_terminal_ambiguity() -> None:
    manager = make_manager()
    result = manager.run(
        prepare(manager),
        ProviderOutcomeUnknownExecutor(),
        empty_workspace(),
    )
    assert result.terminal_outcome is TerminalOutcome.OUTCOME_UNKNOWN
    event = next(event for event in result.events if event.kind == "agent.outcome_unknown")
    assert event.payload == {
        "reason": "provider_outcome_unknown",
        "category": "outcome_unknown",
    }
    assert "safe provider ambiguity" not in repr(event.payload)

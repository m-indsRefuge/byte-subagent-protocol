from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from bsap.canonical import sha256_hex
from bsap.executor import ExecutionCancelled, Executor
from bsap.lifecycle import EventLog, EventStoreFailure, Lifecycle
from bsap.model_protocol import ModelProtocolError
from bsap.model_transport import ModelTransportError
from bsap.models import (
    BsapRequest,
    Budget,
    ContextManifest,
    ExecutionResult,
    ExecutorInfo,
    LifecycleState,
    ParentDisposition,
    PermissionSet,
    PreparedRequest,
    TerminalOutcome,
)
from bsap.receipt import build_receipt
from bsap.reporting import ReportValidationError, validate_report
from bsap.sandbox import (
    BudgetCounter,
    ContextAccessDenied,
    InMemoryWorkspace,
    OutcomeUnknownError,
    SandboxError,
    ToolDispatcher,
    ToolTimeout,
)


class ActiveChildError(RuntimeError):
    pass


class GovernanceValidationError(ValueError):
    pass


@dataclass
class _Record:
    prepared: PreparedRequest
    lifecycle: Lifecycle
    events: EventLog
    created_at: datetime


class SubAgentManager:
    def __init__(
        self,
        *,
        id_factory: Callable[[], str],
        clock: Callable[[], datetime] | None = None,
        event_log_factory: Callable[[str, Callable[[], datetime]], EventLog] | None = None,
    ) -> None:
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._event_log_factory = event_log_factory or (lambda agent_id, clock: EventLog(agent_id, clock))
        self._active_agent_id: str | None = None
        self._records: dict[str, _Record] = {}
        self._results: dict[str, ExecutionResult] = {}
        self._dispositions: dict[str, ParentDisposition] = {}

    def prepare(
        self,
        request: BsapRequest,
        *,
        context_manifest: ContextManifest,
        permissions: PermissionSet,
        budget: Budget,
    ) -> PreparedRequest:
        if self._active_agent_id is not None:
            raise ActiveChildError(f"Active BSAP child already exists: {self._active_agent_id}")
        if permissions.filesystem_write or permissions.external_network or permissions.spawn_subagents:
            raise GovernanceValidationError(
                "BSAP v0.1 forbids write, external-network, and recursive-spawn permissions"
            )
        agent_id = self._id_factory()
        policy = {
            "policy_id": "bsap-v0.1",
            "permissions": permissions,
            "budget": budget,
            "completion_contract": request.completion_contract,
        }
        prepared = PreparedRequest(
            agent_id=agent_id,
            parent_id="BYTE",
            role=request.role,
            objective=request.objective,
            delegation_reason=request.delegation_reason,
            context_manifest=context_manifest,
            permissions=permissions,
            budget=budget,
            completion_contract=request.completion_contract,
            request_sha256=sha256_hex(request),
            context_manifest_sha256=sha256_hex(context_manifest),
            policy_sha256=sha256_hex(policy),
        )
        lifecycle = Lifecycle()
        log = self._event_log_factory(agent_id, self._clock)
        created_at = self._clock()
        log.emit("agent.created", {"role": request.role})
        log.emit("context.validated", {"file_count": len(context_manifest.files)})
        lifecycle.transition(LifecycleState.PREPARED)
        self._records[agent_id] = _Record(prepared, lifecycle, log, created_at)
        self._active_agent_id = agent_id
        return prepared

    def run(
        self,
        prepared: PreparedRequest,
        executor: Executor,
        workspace: InMemoryWorkspace,
    ) -> ExecutionResult:
        record = self._records[prepared.agent_id]
        if self._active_agent_id != prepared.agent_id:
            raise ActiveChildError("Prepared request is not the active BSAP child")
        started_at = self._clock()
        report = None
        try:
            record.lifecycle.transition(LifecycleState.RUNNING)
            record.events.emit("agent.started", {})
            tools = ToolDispatcher(
                workspace=workspace,
                permissions=prepared.permissions,
                budget_counter=BudgetCounter(prepared.budget),
                emit=record.events.emit,
            )
            report = executor.execute(prepared, tools, record.events.emit)
            record.lifecycle.transition(LifecycleState.REPORTING)
            validate_report(report, prepared.completion_contract)
            record.lifecycle.transition(LifecycleState.COMPLETED)
            record.events.emit("agent.completed", {})
        except ExecutionCancelled:
            self._transition_safely(record.lifecycle, LifecycleState.CANCELLED)
            self._emit_safely(record.events, "agent.cancelled", {})
        except EventStoreFailure:
            self._transition_safely(record.lifecycle, LifecycleState.OUTCOME_UNKNOWN)
        except OutcomeUnknownError:
            self._transition_safely(record.lifecycle, LifecycleState.OUTCOME_UNKNOWN)
            self._emit_safely(record.events, "agent.outcome_unknown", {})
        except ContextAccessDenied:
            self._transition_safely(record.lifecycle, LifecycleState.FAILED)
            self._emit_safely(
                record.events,
                "agent.failed",
                {"classification": "FAILED", "reason": "context_denied"},
            )
        except ToolTimeout:
            self._transition_safely(record.lifecycle, LifecycleState.FAILED)
            self._emit_safely(
                record.events,
                "agent.failed",
                {"classification": "FAILED", "reason": "tool_timeout"},
            )
        except ModelTransportError as exc:
            self._transition_safely(record.lifecycle, LifecycleState.FAILED)
            self._emit_safely(
                record.events,
                "agent.failed",
                {
                    "classification": "FAILED",
                    "reason": "provider_failure",
                    "category": exc.category.value,
                },
            )
        except ModelProtocolError as exc:
            self._transition_safely(record.lifecycle, LifecycleState.FAILED)
            self._emit_safely(
                record.events,
                "agent.failed",
                {
                    "classification": "FAILED",
                    "reason": "protocol_failure",
                    "code": exc.code,
                },
            )
        except (SandboxError, ReportValidationError, FileNotFoundError, RuntimeError):
            target = (
                LifecycleState.OUTCOME_UNKNOWN
                if self._has_unclosed_tool(record.events.events)
                else LifecycleState.FAILED
            )
            self._transition_safely(record.lifecycle, target)
            self._emit_safely(record.events, "agent.failed", {"classification": target.value})
        outcome = record.lifecycle.terminal_outcome
        if outcome is None:
            raise RuntimeError("Execution ended without terminal outcome")
        self._transition_safely(record.lifecycle, LifecycleState.TERMINATED)
        self._emit_safely(record.events, "agent.terminated", {})
        finished_at = self._clock()
        receipt = build_receipt(
            prepared=prepared,
            terminal_outcome=outcome,
            events=record.events.events,
            report=report if outcome is TerminalOutcome.COMPLETED else None,
            executor_info=executor.info,
            created_at=record.created_at,
            started_at=started_at,
            finished_at=finished_at,
        )
        result = ExecutionResult(
            agent_id=prepared.agent_id,
            final_state=record.lifecycle.state,
            terminal_outcome=outcome,
            events=record.events.events,
            report=report if outcome is TerminalOutcome.COMPLETED else None,
            receipt=receipt,
        )
        self._results[prepared.agent_id] = result
        self._active_agent_id = None
        return result

    def cancel(self, agent_id: str) -> ExecutionResult:
        record = self._records[agent_id]
        if self._active_agent_id != agent_id:
            raise ActiveChildError("BSAP child is not active")
        if record.lifecycle.state is not LifecycleState.PREPARED:
            raise ActiveChildError("Synchronous EXEC-01 cancellation is supported before RUNNING")
        record.lifecycle.transition(LifecycleState.CANCELLED)
        record.events.emit("agent.cancelled", {"reason": "parent_request"})
        outcome = record.lifecycle.terminal_outcome
        if outcome is None:
            raise RuntimeError("Cancellation did not establish terminal outcome")
        record.lifecycle.transition(LifecycleState.TERMINATED)
        record.events.emit("agent.terminated", {})
        now = self._clock()
        receipt = build_receipt(
            prepared=record.prepared,
            terminal_outcome=outcome,
            events=record.events.events,
            report=None,
            executor_info=ExecutorInfo(type="manager", version="0.1"),
            created_at=record.created_at,
            started_at=None,
            finished_at=now,
        )
        result = ExecutionResult(
            agent_id=agent_id,
            final_state=record.lifecycle.state,
            terminal_outcome=outcome,
            events=record.events.events,
            report=None,
            receipt=receipt,
        )
        self._results[agent_id] = result
        self._active_agent_id = None
        return result

    def record_parent_disposition(self, disposition: ParentDisposition) -> None:
        result = self._results.get(disposition.agent_id)
        if result is None or result.report is None:
            raise ValueError("Parent disposition requires a completed child report")
        self._dispositions[disposition.agent_id] = disposition

    def get_parent_disposition(self, agent_id: str) -> ParentDisposition | None:
        return self._dispositions.get(agent_id)

    @staticmethod
    def _has_unclosed_tool(events) -> bool:
        started = sum(event.kind == "tool.started" for event in events)
        completed = sum(event.kind == "tool.completed" for event in events)
        return started > completed

    @staticmethod
    def _transition_safely(lifecycle: Lifecycle, target: LifecycleState) -> None:
        if lifecycle.state in {
            LifecycleState.COMPLETED,
            LifecycleState.FAILED,
            LifecycleState.CANCELLED,
            LifecycleState.OUTCOME_UNKNOWN,
        } and target is not LifecycleState.TERMINATED:
            return
        lifecycle.transition(target)

    @staticmethod
    def _emit_safely(log: EventLog, kind: str, payload: dict[str, object]) -> None:
        try:
            log.emit(kind, payload)
        except EventStoreFailure:
            return

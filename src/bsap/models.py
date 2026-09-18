from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class LifecycleState(StrEnum):
    REQUESTED = "REQUESTED"
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    TERMINATED = "TERMINATED"


class TerminalOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class ParentDispositionResult(StrEnum):
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED = "rejected"
    REQUIRES_FURTHER_INVESTIGATION = "requires_further_investigation"


@dataclass(frozen=True, slots=True)
class DelegationReason:
    trigger: str
    rationale: str
    expected_value: str


@dataclass(frozen=True, slots=True)
class PermissionSet:
    filesystem_read: bool = False
    filesystem_write: bool = False
    tests_run: bool = False
    external_network: bool = False
    spawn_subagents: bool = False


@dataclass(frozen=True, slots=True)
class Budget:
    max_steps: int
    max_tool_calls: int


@dataclass(frozen=True, slots=True)
class ContextManifest:
    files: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    parent_summary: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompletionContract:
    require: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BsapRequest:
    role: str
    objective: str
    delegation_reason: DelegationReason
    context_requirements: tuple[str, ...]
    requested_capabilities: tuple[str, ...]
    completion_contract: CompletionContract
    protocol: str = "BSAP"
    version: str = "0.1"


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    agent_id: str
    parent_id: str
    role: str
    objective: str
    delegation_reason: DelegationReason
    context_manifest: ContextManifest
    permissions: PermissionSet
    budget: Budget
    completion_contract: CompletionContract
    request_sha256: str
    context_manifest_sha256: str
    policy_sha256: str
    protocol: str = "BSAP"
    version: str = "0.1"
    policy_id: str = "bsap-v0.1"


@dataclass(frozen=True, slots=True)
class Event:
    agent_id: str
    sequence: int
    timestamp: datetime
    kind: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    claim: str


@dataclass(frozen=True, slots=True)
class Evidence:
    finding_id: str
    source: str
    observation: str


@dataclass(frozen=True, slots=True)
class AlternativeHypothesis:
    claim: str
    disposition: str
    basis: str


@dataclass(frozen=True, slots=True)
class BsapReport:
    agent_id: str
    status: str
    findings: tuple[Finding, ...]
    evidence: tuple[Evidence, ...]
    alternative_hypotheses: tuple[AlternativeHypothesis, ...]
    uncertainties: tuple[str, ...]
    recommended_next_action: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParentDisposition:
    agent_id: str
    result: ParentDispositionResult
    accepted_findings: tuple[str, ...]
    rejected_findings: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class ExecutorInfo:
    type: str
    version: str
    transport: str | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class Receipt:
    protocol: str
    version: str
    agent_id: str
    parent_id: str
    request_sha256: str
    context_manifest_sha256: str
    policy_sha256: str
    executor: ExecutorInfo
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime
    terminal_state: TerminalOutcome
    event_count: int
    report_sha256: str | None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    agent_id: str
    final_state: LifecycleState
    terminal_outcome: TerminalOutcome
    events: tuple[Event, ...]
    report: BsapReport | None
    receipt: Receipt


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: Mapping[str, object]

from datetime import UTC, datetime

import pytest

from bsap.executor import ScriptedDeterministicExecutor
from bsap.manager import ActiveChildError, SubAgentManager
from bsap.models import (
    AlternativeHypothesis,
    BsapReport,
    BsapRequest,
    Budget,
    CompletionContract,
    ContextManifest,
    DelegationReason,
    Evidence,
    Finding,
    ParentDisposition,
    ParentDispositionResult,
    PermissionSet,
    TerminalOutcome,
    ToolCall,
)
from bsap.sandbox import InMemoryWorkspace


def fixed_clock() -> datetime:
    return datetime(2026, 9, 17, 21, 20, tzinfo=UTC)


def ids():
    values = iter(("BSA-000001", "BSA-000002", "BSA-000003"))
    return lambda: next(values)


def request() -> BsapRequest:
    return BsapRequest(
        role="investigator",
        objective="inspect timeout conversion",
        delegation_reason=DelegationReason("verification", "reduce bias", "evidence"),
        context_requirements=("relevant files",),
        requested_capabilities=("repository.read", "repository.search"),
        completion_contract=CompletionContract(
            require=("findings", "evidence", "alternative_hypotheses", "uncertainties", "recommended_next_action")
        ),
    )


def manifest() -> ContextManifest:
    return ContextManifest(files=("settings.py", "client.py"), observations=("timeout failure",))


def permissions() -> PermissionSet:
    return PermissionSet(filesystem_read=True, tests_run=True)


def workspace() -> InMemoryWorkspace:
    return InMemoryWorkspace(
        files={"settings.py": "timeout_ms", "client.py": "timeout_seconds"},
        allowed_files=("settings.py", "client.py"),
    )


def report_builder(results):
    assert len(results) == 2
    return BsapReport(
        agent_id="BSA-000001",
        status="completed",
        findings=(Finding(id="F-1", claim="missing conversion"),),
        evidence=(Evidence(finding_id="F-1", source="settings.py", observation="direct copy"),),
        alternative_hypotheses=(AlternativeHypothesis("client converts", "rejected", "client source"),),
        uncertainties=(),
        recommended_next_action=("fix boundary",),
    )


def executor() -> ScriptedDeterministicExecutor:
    return ScriptedDeterministicExecutor(
        actions=(
            ToolCall("repository.read", {"path": "settings.py"}),
            ToolCall("repository.read", {"path": "client.py"}),
        ),
        report_builder=report_builder,
    )


def test_prepare_freezes_identity_hashes_and_single_active_child() -> None:
    manager = SubAgentManager(id_factory=ids(), clock=fixed_clock)
    prepared = manager.prepare(
        request(),
        context_manifest=manifest(),
        permissions=permissions(),
        budget=Budget(max_steps=10, max_tool_calls=5),
    )
    assert prepared.agent_id == "BSA-000001"
    assert prepared.parent_id == "BYTE"
    assert len(prepared.request_sha256) == 64
    assert len(prepared.context_manifest_sha256) == 64
    assert len(prepared.policy_sha256) == 64
    with pytest.raises(ActiveChildError):
        manager.prepare(
            request(),
            context_manifest=manifest(),
            permissions=permissions(),
            budget=Budget(max_steps=10, max_tool_calls=5),
        )


def test_happy_path_completes_terminates_and_releases_slot() -> None:
    manager = SubAgentManager(id_factory=ids(), clock=fixed_clock)
    prepared = manager.prepare(
        request(), context_manifest=manifest(), permissions=permissions(), budget=Budget(10, 5)
    )
    result = manager.run(prepared, executor(), workspace())
    assert result.terminal_outcome is TerminalOutcome.COMPLETED
    assert result.final_state.value == "TERMINATED"
    assert result.report is not None
    assert result.receipt.report_sha256 is not None
    next_prepared = manager.prepare(
        request(), context_manifest=manifest(), permissions=permissions(), budget=Budget(10, 5)
    )
    assert next_prepared.agent_id == "BSA-000002"


def test_parent_disposition_is_separate_from_child_completion() -> None:
    manager = SubAgentManager(id_factory=ids(), clock=fixed_clock)
    prepared = manager.prepare(
        request(), context_manifest=manifest(), permissions=permissions(), budget=Budget(10, 5)
    )
    result = manager.run(prepared, executor(), workspace())
    assert manager.get_parent_disposition(result.agent_id) is None
    disposition = ParentDisposition(
        agent_id=result.agent_id,
        result=ParentDispositionResult.REJECTED,
        accepted_findings=(),
        rejected_findings=("F-1",),
        rationale="parent rejected conclusion",
    )
    manager.record_parent_disposition(disposition)
    assert manager.get_parent_disposition(result.agent_id) == disposition
    assert result.terminal_outcome is TerminalOutcome.COMPLETED


def test_failed_attempt_does_not_retry_and_next_attempt_gets_new_id() -> None:
    manager = SubAgentManager(id_factory=ids(), clock=fixed_clock)
    prepared = manager.prepare(
        request(), context_manifest=manifest(), permissions=permissions(), budget=Budget(10, 0)
    )
    failed = manager.run(prepared, executor(), workspace())
    assert failed.terminal_outcome is TerminalOutcome.FAILED
    next_prepared = manager.prepare(
        request(), context_manifest=manifest(), permissions=permissions(), budget=Budget(10, 5)
    )
    assert next_prepared.agent_id == "BSA-000002"

@pytest.mark.parametrize(
    "permissions_override",
    [
        PermissionSet(filesystem_read=True, filesystem_write=True),
        PermissionSet(filesystem_read=True, external_network=True),
        PermissionSet(filesystem_read=True, spawn_subagents=True),
    ],
)
def test_prepare_rejects_permissions_forbidden_by_v01(permissions_override: PermissionSet) -> None:
    from bsap.manager import GovernanceValidationError

    manager = SubAgentManager(id_factory=ids(), clock=fixed_clock)
    with pytest.raises(GovernanceValidationError):
        manager.prepare(
            request(),
            context_manifest=manifest(),
            permissions=permissions_override,
            budget=Budget(10, 5),
        )

from datetime import UTC, datetime

from bsap.models import (
    BsapReport,
    Budget,
    CompletionContract,
    ContextManifest,
    DelegationReason,
    Evidence,
    ExecutorInfo,
    Finding,
    PermissionSet,
    PreparedRequest,
    TerminalOutcome,
)
from bsap.receipt import build_receipt


def prepared() -> PreparedRequest:
    return PreparedRequest(
        agent_id="BSA-1",
        parent_id="BYTE",
        role="investigator",
        objective="inspect timeout conversion",
        delegation_reason=DelegationReason("verification", "reduce bias", "evidence"),
        context_manifest=ContextManifest(files=("settings.py",)),
        permissions=PermissionSet(filesystem_read=True, tests_run=True),
        budget=Budget(max_steps=10, max_tool_calls=5),
        completion_contract=CompletionContract(require=("findings", "evidence")),
        request_sha256="a" * 64,
        context_manifest_sha256="b" * 64,
        policy_sha256="c" * 64,
    )


def report(claim: str = "missing conversion") -> BsapReport:
    return BsapReport(
        agent_id="BSA-1",
        status="completed",
        findings=(Finding(id="F-1", claim=claim),),
        evidence=(Evidence(finding_id="F-1", source="settings.py", observation="direct copy"),),
        alternative_hypotheses=(),
        uncertainties=(),
        recommended_next_action=("fix boundary",),
    )


def test_receipt_binds_frozen_artifacts_and_report_hash() -> None:
    now = datetime(2026, 9, 17, 21, 10, tzinfo=UTC)
    receipt = build_receipt(
        prepared=prepared(),
        terminal_outcome=TerminalOutcome.COMPLETED,
        events=(),
        report=report(),
        executor_info=ExecutorInfo(type="deterministic", version="0.1"),
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    assert receipt.request_sha256 == "a" * 64
    assert receipt.context_manifest_sha256 == "b" * 64
    assert receipt.policy_sha256 == "c" * 64
    assert receipt.report_sha256 is not None
    assert receipt.terminal_state is TerminalOutcome.COMPLETED


def test_report_change_changes_report_hash_only() -> None:
    now = datetime(2026, 9, 17, 21, 10, tzinfo=UTC)
    kwargs = {
        "prepared": prepared(),
        "terminal_outcome": TerminalOutcome.COMPLETED,
        "events": (),
        "executor_info": ExecutorInfo(type="deterministic", version="0.1"),
        "created_at": now,
        "started_at": now,
        "finished_at": now,
    }
    first = build_receipt(report=report("first"), **kwargs)
    second = build_receipt(report=report("second"), **kwargs)
    assert first.report_sha256 != second.report_sha256
    assert first.request_sha256 == second.request_sha256
    assert first.context_manifest_sha256 == second.context_manifest_sha256
    assert first.policy_sha256 == second.policy_sha256


def test_no_report_produces_no_report_hash() -> None:
    now = datetime(2026, 9, 17, 21, 10, tzinfo=UTC)
    receipt = build_receipt(
        prepared=prepared(),
        terminal_outcome=TerminalOutcome.FAILED,
        events=(),
        report=None,
        executor_info=ExecutorInfo(type="deterministic", version="0.1"),
        created_at=now,
        started_at=None,
        finished_at=now,
    )
    assert receipt.report_sha256 is None

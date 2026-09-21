from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from bsap.byte_mcp_transport import (
    ByteMCPNvidiaTransport,
    StreamableHttpNvidiaQueryInvoker,
)
from bsap.canonical import canonical_json
from bsap.manager import SubAgentManager
from bsap.model_executor import ModelExecutor
from bsap.model_transport import ModelTransport
from bsap.models import (
    BsapRequest,
    Budget,
    CompletionContract,
    ContextManifest,
    DelegationReason,
    ExecutionResult,
    ParentDisposition,
    ParentDispositionResult,
    PermissionSet,
    TerminalOutcome,
)
from bsap.sandbox import HostTestWorkspace
from bsap.test_runner import AllowlistedTestRunner, ApprovedTest


def _fixture_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "exec02_canary"


def _agent_id() -> str:
    return f"BSA-LIVE-{uuid.uuid4().hex[:12].upper()}"


def run_live_canary(
    transport: ModelTransport,
) -> tuple[SubAgentManager, ExecutionResult]:
    fixture_dir = _fixture_directory()
    settings_path = fixture_dir / "settings.py"
    client_path = fixture_dir / "client.py"
    test_path = fixture_dir / "check_timeout.py"

    files = {
        "settings.py": settings_path.read_text(encoding="utf-8"),
        "client.py": client_path.read_text(encoding="utf-8"),
    }

    request = BsapRequest(
        role="investigator",
        objective=(
            "Determine why 5000 milliseconds reaches the HTTP client as "
            "5000 seconds instead of 5 seconds."
        ),
        delegation_reason=DelegationReason(
            trigger="independent_investigation",
            rationale="Use a bounded read-only worker to establish the failure boundary.",
            expected_value="Return an evidence-backed diagnosis without modifying code.",
        ),
        context_requirements=(
            "settings.py",
            "client.py",
            "approved timeout-conversion test",
        ),
        requested_capabilities=(
            "repository.read",
            "repository.search",
            "tests.run",
        ),
        completion_contract=CompletionContract(
            require=(
                "findings",
                "evidence",
                "alternative_hypotheses",
                "uncertainties",
                "recommended_next_action",
            )
        ),
    )
    manifest = ContextManifest(
        files=("settings.py", "client.py"),
        observations=(
            "A 5000 millisecond configuration value is observed as timeout=5000 seconds.",
        ),
        constraints=(
            "read-only investigation",
            "use only approved BSAP tools",
            "no arbitrary shell",
        ),
        parent_summary=(
            "External configuration expresses request timeout in milliseconds.",
            "Internal HTTP client timeout representation is seconds.",
        ),
        excluded=(
            "conversation history",
            "personal memory",
            "unrelated repositories",
            "network access",
        ),
    )
    permissions = PermissionSet(
        filesystem_read=True,
        tests_run=True,
        filesystem_write=False,
        external_network=False,
        spawn_subagents=False,
    )
    budget = Budget(max_steps=6, max_tool_calls=4)

    runner = AllowlistedTestRunner(
        tests=(
            ApprovedTest(
                name="timeout-conversion",
                command=(sys.executable, str(test_path.name)),
                cwd=fixture_dir,
                timeout_seconds=10.0,
                max_output_chars=4000,
            ),
        )
    )
    workspace = HostTestWorkspace(
        files=files,
        allowed_files=manifest.files,
        test_runner=runner,
    )
    manager = SubAgentManager(id_factory=_agent_id)
    prepared = manager.prepare(
        request,
        context_manifest=manifest,
        permissions=permissions,
        budget=budget,
    )
    result = manager.run(
        prepared,
        ModelExecutor(transport=transport),
        workspace,
    )
    return manager, result


def disposition_from_json(
    manager: SubAgentManager,
    result: ExecutionResult,
    raw: str,
) -> ParentDisposition:
    if result.terminal_outcome is not TerminalOutcome.COMPLETED or result.report is None:
        raise ValueError("Parent disposition requires a completed report")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Parent disposition must be valid JSON") from exc

    if not isinstance(payload, dict) or set(payload) != {
        "result",
        "accepted_findings",
        "rejected_findings",
        "rationale",
    }:
        raise ValueError("Parent disposition does not match the required schema")

    raw_result = payload["result"]
    if not isinstance(raw_result, str):
        raise TypeError("Parent disposition result must be a string")
    try:
        disposition_result = ParentDispositionResult(raw_result)
    except ValueError as exc:
        raise ValueError("Unknown parent disposition result") from exc

    accepted = payload["accepted_findings"]
    rejected = payload["rejected_findings"]
    rationale = payload["rationale"]
    if (
        not isinstance(accepted, list)
        or any(not isinstance(item, str) for item in accepted)
        or not isinstance(rejected, list)
        or any(not isinstance(item, str) for item in rejected)
        or not isinstance(rationale, str)
        or not rationale.strip()
    ):
        raise ValueError("Parent disposition fields have invalid types")

    finding_ids = {finding.id for finding in result.report.findings}
    selected_ids = set(accepted) | set(rejected)
    if not selected_ids.issubset(finding_ids):
        raise ValueError("Parent disposition references an unknown finding")
    if set(accepted) & set(rejected):
        raise ValueError("A finding cannot be both accepted and rejected")

    disposition = ParentDisposition(
        agent_id=result.agent_id,
        result=disposition_result,
        accepted_findings=tuple(accepted),
        rejected_findings=tuple(rejected),
        rationale=rationale.strip(),
    )
    manager.record_parent_disposition(disposition)
    return disposition


_SAFE_DIAGNOSTIC_EVENTS = frozenset(
    {
        "provider.failed",
        "protocol.failed",
        "agent.failed",
        "agent.outcome_unknown",
        "permission.denied",
        "budget.exhausted",
        "tool.failed",
        "context.denied",
    }
)


def _safe_failure_diagnostics(result: ExecutionResult) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "kind": event.kind,
            "payload": dict(event.payload),
            "sequence": event.sequence,
        }
        for event in result.events
        if event.kind in _SAFE_DIAGNOSTIC_EVENTS
    )


def _print_result(result: ExecutionResult) -> None:
    print(f"agent_id={result.agent_id}")
    print(f"terminal_outcome={result.terminal_outcome.value}")
    if result.report is not None:
        print("findings=" + canonical_json(result.report.findings))
        print("evidence=" + canonical_json(result.report.evidence))
        print("uncertainties=" + canonical_json(result.report.uncertainties))
        print(
            "recommended_next_action="
            + canonical_json(result.report.recommended_next_action)
        )
    elif result.terminal_outcome is not TerminalOutcome.COMPLETED:
        print("failure_diagnostics=" + canonical_json(_safe_failure_diagnostics(result)))
    print("executor=" + canonical_json(result.receipt.executor))
    print(f"request_sha256={result.receipt.request_sha256}")
    print(f"context_manifest_sha256={result.receipt.context_manifest_sha256}")
    print(f"policy_sha256={result.receipt.policy_sha256}")
    print(f"report_sha256={result.receipt.report_sha256}")


def main() -> None:
    mcp_url = os.getenv("BYTE_MCP_URL", "http://127.0.0.1:8000/mcp")
    invoker = StreamableHttpNvidiaQueryInvoker(mcp_url)
    invoker.probe_schema()

    transport = ByteMCPNvidiaTransport(
        invoker=invoker,
        model_alias="lightning",
    )
    manager, result = run_live_canary(transport)
    _print_result(result)

    if result.terminal_outcome is not TerminalOutcome.COMPLETED:
        return

    print("PARENT_DISPOSITION_REQUIRED")
    raw = sys.stdin.readline()
    if not raw:
        raise SystemExit(2)
    try:
        disposition = disposition_from_json(manager, result, raw)
    except ValueError:
        print("parent_disposition_error=invalid")
        raise SystemExit(2) from None
    print(f"parent_disposition={disposition.result.value}")


if __name__ == "__main__":
    main()

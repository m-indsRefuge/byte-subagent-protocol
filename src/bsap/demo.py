from __future__ import annotations

from bsap.executor import ScriptedDeterministicExecutor
from bsap.manager import SubAgentManager
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
    ToolCall,
)
from bsap.sandbox import InMemoryWorkspace

SETTINGS_SOURCE = '''from dataclasses import dataclass

@dataclass(frozen=True)
class HttpSettings:
    request_timeout_seconds: int


def load_http_settings(raw: dict[str, str]) -> HttpSettings:
    return HttpSettings(
        request_timeout_seconds=int(raw["request_timeout_ms"]),
    )
'''

CLIENT_SOURCE = '''def build_request_options(settings):
    return {"timeout": settings.request_timeout_seconds}
'''


def _report_builder(results) -> BsapReport:
    settings_source = str(results[0]["content"])
    client_source = str(results[1]["content"])
    search_matches = results[2]["matches"]

    if "request_timeout_ms" not in settings_source or "request_timeout_seconds" not in client_source:
        raise RuntimeError("Controlled timeout fixture does not match the expected contract")
    if not search_matches:
        raise RuntimeError("Expected timeout evidence was not found")

    return BsapReport(
        agent_id="BSA-DEMO-000001",
        status="completed",
        findings=(
            Finding(
                id="F-001",
                claim="The milliseconds-to-seconds conversion is missing at the configuration boundary.",
            ),
        ),
        evidence=(
            Evidence(
                finding_id="F-001",
                source="settings.py",
                observation="request_timeout_ms is converted to int and copied directly into request_timeout_seconds.",
            ),
            Evidence(
                finding_id="F-001",
                source="client.py",
                observation="The client consumes request_timeout_seconds directly as timeout with no later conversion.",
            ),
        ),
        alternative_hypotheses=(
            AlternativeHypothesis(
                claim="The HTTP client performs the milliseconds-to-seconds conversion later.",
                disposition="rejected",
                basis="client.py passes request_timeout_seconds directly to the timeout option.",
            ),
        ),
        uncertainties=(),
        recommended_next_action=(
            "Convert milliseconds to seconds in the configuration loader and add regression coverage.",
        ),
    )


def build_timeout_demo():
    manager = SubAgentManager(id_factory=lambda: "BSA-DEMO-000001")
    request = BsapRequest(
        role="investigator",
        objective="Determine why the deterministic HTTP timeout test reports 5000 seconds instead of 5 seconds.",
        delegation_reason=DelegationReason(
            trigger="independent_investigation",
            rationale="A bounded independent investigation can establish the defective representation boundary.",
            expected_value="Return an evidence-backed root-cause report without modifying code.",
        ),
        context_requirements=("settings.py", "client.py", "failing observation", "unit contract"),
        requested_capabilities=("repository.read", "repository.search"),
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
        observations=("5000 milliseconds produced timeout=5000 seconds",),
        constraints=("investigation only", "no code modification"),
        parent_summary=("External configuration is milliseconds; internal timeout representation is seconds.",),
        excluded=("conversation history", "personal memory", "unrelated project state"),
    )
    prepared = manager.prepare(
        request,
        context_manifest=manifest,
        permissions=PermissionSet(filesystem_read=True, tests_run=True),
        budget=Budget(max_steps=10, max_tool_calls=10),
    )
    workspace = InMemoryWorkspace(
        files={"settings.py": SETTINGS_SOURCE, "client.py": CLIENT_SOURCE, "secret.py": "unrelated"},
        allowed_files=manifest.files,
    )
    executor = ScriptedDeterministicExecutor(
        actions=(
            ToolCall("repository.read", {"path": "settings.py"}),
            ToolCall("repository.read", {"path": "client.py"}),
            ToolCall("repository.search", {"query": "request_timeout_ms"}),
        ),
        report_builder=_report_builder,
    )
    return manager, prepared, executor, workspace


def run_timeout_demo():
    manager, prepared, executor, workspace = build_timeout_demo()
    result = manager.run(prepared, executor, workspace)
    if result.report is None:
        raise RuntimeError("Deterministic timeout demo did not produce a completed report")
    disposition = ParentDisposition(
        agent_id=result.agent_id,
        result=ParentDispositionResult.ACCEPTED,
        accepted_findings=tuple(finding.id for finding in result.report.findings),
        rejected_findings=(),
        rationale="Each finding is directly supported by the frozen source context.",
    )
    manager.record_parent_disposition(disposition)
    return result, disposition


def main() -> None:
    result, disposition = run_timeout_demo()
    print(f"agent_id={result.agent_id}")
    print("events=" + ",".join(event.kind for event in result.events))
    print(f"terminal_outcome={result.terminal_outcome.value}")
    print(f"finding={result.report.findings[0].id if result.report else 'NONE'}")
    print(f"request_sha256={result.receipt.request_sha256}")
    print(f"context_manifest_sha256={result.receipt.context_manifest_sha256}")
    print(f"policy_sha256={result.receipt.policy_sha256}")
    print(f"report_sha256={result.receipt.report_sha256}")
    print(f"parent_disposition={disposition.result.value}")


if __name__ == "__main__":
    main()

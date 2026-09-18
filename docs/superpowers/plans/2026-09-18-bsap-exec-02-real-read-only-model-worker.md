# BSAP-EXEC-02 Real Read-Only Model Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add the first genuinely independent, read-only BSAP model worker using Nemotron 3.5 Lightning through the existing Byte-MCP NVIDIA layer while preserving EXEC-01 governance.

**Architecture:** Keep SubAgentManager and ToolDispatcher authoritative. Add a provider-neutral ModelTransport, a strict JSON child protocol, a bounded ModelExecutor loop, a host-side allowlisted test runner, and a Byte-MCP/NVIDIA transport adapter. Deterministic fake-transport tests prove the control plane before a single live Lightning canary.

**Tech Stack:** Python 3.12+, standard library for the BSAP core, pytest 9+, Ruff 0.16+, optional mcp==1.28.1 for the live Byte-MCP Streamable HTTP adapter.

**Spec:** docs/superpowers/specs/2026-09-18-bsap-exec-02-real-read-only-model-worker-design.md

## Global Constraints

- Python remains >=3.12.
- EXEC-01 behavior and tests remain green throughout.
- One active BSAP child at a time; delegation depth remains one.
- The child remains filesystem-write=false, external-network=false, spawn-subagents=false.
- Provider communication is trusted host infrastructure, not a child capability.
- The child may autonomously choose only repository.read, repository.search, and tests.run.
- Every model turn returns exactly one strict JSON envelope: tool_request or final_report.
- No chain-of-thought is requested, stored, or required.
- The assignment, context, permissions, budget, and completion contract remain immutable after RUNNING.
- One child execution may contain multiple model turns, but there are no hidden provider retries.
- A retry after provider failure receives a new BSAP execution identity.
- tests.run accepts only parent-approved stable test identifiers; the model never supplies shell text.
- Byte-MCP remains the owner of NVIDIA credentials.
- The first live model alias is lightning, currently mapped by the governed Byte-MCP runtime to nvidia/nemotron-3.5-lightning-30b-a3b.
- The live Byte-MCP tool contract expected by this plan is nvidia_query(prompt, model, system_prompt); runtime schema drift is a hard stop before a provider call.
- The public Byte-MCP main branch does not contain the later NVIDIA runtime overlay, so the live tool schema must be validated against the running Byte-MCP instance rather than inferred from the public source tree.
- No write-capable worker, arbitrary shell, web access, recursive delegation, persistent child memory, model switching, concurrency, or background execution is added in EXEC-02.
- FAILURE_MAP.md must be updated before the milestone is complete.

---

## File Structure

Create or modify these focused units:

- src/bsap/model_transport.py — provider-neutral model request/response contracts, transport protocol, normalized transport failures.
- src/bsap/model_protocol.py — strict JSON action parsing into typed tool requests or final reports.
- src/bsap/prompting.py — deterministic child system contract, initial task message, and tool-result messages.
- src/bsap/model_executor.py — bounded iterative model/tool loop implementing Executor.
- src/bsap/test_runner.py — allowlisted host-side subprocess execution with no shell, timeout, and bounded output.
- src/bsap/sandbox.py — integrate real allowlisted tests while preserving frozen read/search semantics.
- src/bsap/manager.py — classify model protocol/provider failures without weakening existing failure semantics.
- src/bsap/models.py — extend ExecutorInfo with optional model provenance.
- src/bsap/byte_mcp_transport.py — Byte-MCP NVIDIA transport plus live schema guard.
- src/bsap/live_canary.py — first bounded live Lightning investigation harness.
- tests/test_model_transport.py — transport contracts/provenance.
- tests/test_model_protocol.py — strict action/report envelope parsing.
- tests/test_prompting.py — prompt/context isolation.
- tests/test_model_executor.py — iterative tool loop and no-retry behavior.
- tests/test_test_runner.py — real allowlisted tests, timeout, output bounds, shell denial by construction.
- tests/test_byte_mcp_transport.py — Byte-MCP adapter/schema normalization without live provider use.
- tests/test_exec02_end_to_end.py — deterministic full EXEC-02 path using FakeModelTransport.
- tests/fixtures/exec02_canary/settings.py — deliberately defective canary source.
- tests/fixtures/exec02_canary/client.py — canary consumer.
- tests/fixtures/exec02_canary/check_timeout.py — approved canary test command.
- pyproject.toml — optional NVIDIA/MCP integration dependency only.
- README.md — EXEC-02 usage/status.
- FAILURE_MAP.md — all new model/provider/test failure surfaces.
- docs/EXEC02-LIVE-CANARY.md — exact live acceptance procedure and recorded outcome.

---

### Task 1: Provider-neutral model transport and receipt provenance

**Files:**
- Create: src/bsap/model_transport.py
- Modify: src/bsap/models.py
- Test: tests/test_model_transport.py
- Test: tests/test_receipt.py

**Interfaces:**
- Produces: ModelMessage(role: str, content: str)
- Produces: ModelRequest(system_prompt: str, messages: tuple[ModelMessage, ...])
- Produces: ModelResponse(text: str)
- Produces: ProviderFailureCategory
- Produces: ModelTransportError(category: ProviderFailureCategory, safe_message: str)
- Produces: ModelTransport protocol with transport_name, model_name, and send(request) -> ModelResponse
- Extends: ExecutorInfo with transport: str | None and model: str | None

- [ ] **Step 1: Write failing provenance and transport-contract tests**

Create tests/test_model_transport.py:

~~~python
from dataclasses import FrozenInstanceError

import pytest

from bsap.model_transport import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
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
~~~

Add to tests/test_receipt.py:

~~~python
def test_receipt_preserves_model_executor_provenance() -> None:
    now = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
    receipt = build_receipt(
        prepared=prepared(),
        terminal_outcome=TerminalOutcome.FAILED,
        events=(),
        report=None,
        executor_info=ExecutorInfo(
            type="model",
            version="0.2",
            transport="byte-mcp-nvidia",
            model="lightning",
        ),
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    assert receipt.executor.transport == "byte-mcp-nvidia"
    assert receipt.executor.model == "lightning"
~~~

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

~~~powershell
python -m pytest tests/test_model_transport.py tests/test_receipt.py -q
~~~

Expected: FAIL because model_transport.py does not exist and ExecutorInfo lacks transport/model.

- [ ] **Step 3: Implement the transport contracts**

Create src/bsap/model_transport.py:

~~~python
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
~~~

Modify ExecutorInfo in src/bsap/models.py:

~~~python
@dataclass(frozen=True, slots=True)
class ExecutorInfo:
    type: str
    version: str
    transport: str | None = None
    model: str | None = None
~~~

Do not change existing deterministic executor construction; its new fields remain None.

- [ ] **Step 4: Run focused tests and the existing receipt/hash tests**

Run:

~~~powershell
python -m pytest tests/test_model_transport.py tests/test_receipt.py tests/test_models_and_hashing.py -q
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add src/bsap/model_transport.py src/bsap/models.py tests/test_model_transport.py tests/test_receipt.py
git commit -m "feat: add BSAP model transport contracts"
~~~

---

### Task 2: Strict JSON child action/report protocol

**Files:**
- Create: src/bsap/model_protocol.py
- Test: tests/test_model_protocol.py

**Interfaces:**
- Produces: ToolRequestAction(tool: str, arguments: Mapping[str, object])
- Produces: FinalReportAction(report: BsapReport)
- Produces: ModelProtocolError(code: str, safe_message: str)
- Produces: ActionParser.parse(text: str, agent_id: str) -> ToolRequestAction | FinalReportAction
- Consumes: BsapReport, Finding, Evidence, AlternativeHypothesis

- [ ] **Step 1: Write strict parser tests**

Create tests/test_model_protocol.py with tests for:
- valid repository.read tool_request;
- valid repository.search tool_request;
- valid tests.run tool_request;
- valid final_report converted to BsapReport with the supplied agent_id;
- prose surrounding JSON rejected;
- invalid JSON rejected;
- unknown envelope type rejected;
- unknown tool rejected;
- missing or extra tool arguments rejected;
- non-string path/query/name rejected;
- extra top-level keys rejected;
- malformed nested finding/evidence/alternative-hypothesis objects rejected.

Use this representative happy-path test:

~~~python
import json

from bsap.model_protocol import ActionParser, FinalReportAction, ToolRequestAction


def test_parse_read_tool_request() -> None:
    action = ActionParser().parse(
        json.dumps(
            {
                "type": "tool_request",
                "tool": "repository.read",
                "arguments": {"path": "settings.py"},
            }
        ),
        agent_id="BSA-2",
    )
    assert action == ToolRequestAction(
        tool="repository.read",
        arguments={"path": "settings.py"},
    )


def test_parse_final_report_injects_frozen_agent_id() -> None:
    action = ActionParser().parse(
        json.dumps(
            {
                "type": "final_report",
                "report": {
                    "status": "completed",
                    "findings": [{"id": "F-1", "claim": "conversion is missing"}],
                    "evidence": [
                        {
                            "finding_id": "F-1",
                            "source": "settings.py",
                            "observation": "5000 is copied directly",
                        }
                    ],
                    "alternative_hypotheses": [
                        {
                            "claim": "client converts later",
                            "disposition": "rejected",
                            "basis": "client consumes the value directly",
                        }
                    ],
                    "uncertainties": [],
                    "recommended_next_action": ["convert milliseconds at the loader boundary"],
                },
            }
        ),
        agent_id="BSA-2",
    )
    assert isinstance(action, FinalReportAction)
    assert action.report.agent_id == "BSA-2"
    assert action.report.findings[0].id == "F-1"
~~~

Use this representative rejection test:

~~~python
import pytest

from bsap.model_protocol import ActionParser, ModelProtocolError


def test_prose_wrapped_json_is_rejected() -> None:
    with pytest.raises(ModelProtocolError) as exc_info:
        parse_model_action(
            'Here is my answer: {"type":"tool_request","tool":"repository.read","arguments":{"path":"a.py"}}',
            agent_id="BSA-2",
        )
    assert exc_info.value.code == "invalid_json"
~~~

- [ ] **Step 2: Run parser tests and confirm RED**

~~~powershell
python -m pytest tests/test_model_protocol.py -q
~~~

Expected: FAIL because model_protocol.py does not exist.

- [ ] **Step 3: Implement exact-schema parsing**

Create immutable ToolRequestAction and FinalReportAction dataclasses. Implement ModelProtocolError with a short code and safe message. Implement ActionParser as the single parsing component; its parse method performs all envelope/schema conversion and never executes tools.

Use json.loads(text) directly. Do not strip prose, search for braces, repair JSON, or retry parsing.

Require exact top-level key sets:
- tool_request: type, tool, arguments
- final_report: type, report

Require exact tool argument schemas:
- repository.read -> {"path": str}
- repository.search -> {"query": str}
- tests.run -> {"name": str}

Require exact final report keys:
- status
- findings
- evidence
- alternative_hypotheses
- uncertainties
- recommended_next_action

Construct Finding, Evidence, and AlternativeHypothesis only from exact key sets. Reject bool/int/null where strings or arrays of strings are required. Preserve report validation as a second independent boundary in reporting.py; the parser validates shape, validate_report validates completion semantics.

- [ ] **Step 4: Run parser and reporting tests**

~~~powershell
python -m pytest tests/test_model_protocol.py tests/test_reporting.py -q
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add src/bsap/model_protocol.py tests/test_model_protocol.py
git commit -m "feat: add strict BSAP model action protocol"
~~~

---

### Task 3: Deterministic prompt and conversation construction

**Files:**
- Create: src/bsap/prompting.py
- Test: tests/test_prompting.py

**Interfaces:**
- Produces: PromptBuilder.system_prompt(prepared: PreparedRequest) -> str
- Produces: PromptBuilder.initial_messages(prepared: PreparedRequest) -> tuple[ModelMessage, ...]
- Produces: PromptBuilder.tool_result_message(tool: str, arguments: Mapping[str, object], result: Mapping[str, object]) -> ModelMessage
- Consumes: canonical_json, PreparedRequest, ModelMessage

- [ ] **Step 1: Write prompt-isolation and deterministic-output tests**

Create tests/test_prompting.py. Build a PreparedRequest containing files, observations, constraints, parent_summary, excluded entries, permissions, budget, and completion contract.

Assert:
- two calls produce byte-identical strings/messages;
- the system prompt names only repository.read, repository.search, tests.run;
- it explicitly says return one JSON object and no prose;
- it explicitly denies writes/network/subagent spawning;
- the initial user message contains objective, delegation reason, frozen ContextManifest, budget, and completion contract;
- it contains no fields not present in PreparedRequest;
- tool results are represented as deterministic JSON with type=tool_result.

Representative test:

~~~python
def test_tool_result_message_is_deterministic_json() -> None:
    message = PromptBuilder().tool_result_message(
        "repository.read",
        {"path": "settings.py"},
        {"path": "settings.py", "content": "timeout_ms"},
    )
    assert message.role == "user"
    assert message.content == (
        '{"arguments":{"path":"settings.py"},'
        '"result":{"content":"timeout_ms","path":"settings.py"},'
        '"tool":"repository.read","type":"tool_result"}'
    )
~~~

- [ ] **Step 2: Run prompting tests and confirm RED**

~~~powershell
python -m pytest tests/test_prompting.py -q
~~~

Expected: FAIL because prompting.py does not exist.

- [ ] **Step 3: Implement PromptBuilder**

Use canonical_json for all machine-readable child/task and tool-result payloads.

The system prompt must include this behavioral contract in concise form:
- You are a bounded BSAP investigator.
- Use only the supplied tools.
- You cannot write files, access the network, invoke providers, or spawn agents.
- Do not reveal hidden reasoning.
- Return exactly one JSON object per turn.
- Tool envelopes and final-report envelopes must match the documented schemas.
- Stop when sufficient evidence supports a completion-contract-valid report.
- If evidence is insufficient, represent that in uncertainties rather than inventing facts.

The initial user message must be a canonical JSON object with:
- role
- objective
- delegation_reason
- context_manifest
- permissions
- budget
- completion_contract

Do not inject external conversation history or memory.

- [ ] **Step 4: Run prompting plus canonical-hash tests**

~~~powershell
python -m pytest tests/test_prompting.py tests/test_models_and_hashing.py -q
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add src/bsap/prompting.py tests/test_prompting.py
git commit -m "feat: build deterministic BSAP model prompts"
~~~

---

### Task 4: Bounded iterative ModelExecutor

**Files:**
- Create: src/bsap/model_executor.py
- Test: tests/test_model_executor.py

**Interfaces:**
- Produces: ModelExecutor(transport: ModelTransport, prompt_builder: PromptBuilder | None = None)
- Implements: Executor.execute(prepared, tools, emit) -> BsapReport
- Produces ExecutorInfo(type="model", version="0.2", transport=transport.transport_name, model=transport.model_name)
- Consumes: ActionParser, ToolDispatcher, ModelRequest, ModelResponse

- [ ] **Step 1: Create a deterministic FakeModelTransport in the test module**

Use a queue of exact model responses and count every send call:

~~~python
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
        from bsap.model_transport import ModelResponse

        self.requests.append(request)
        return ModelResponse(next(self._responses))
~~~

- [ ] **Step 2: Write failing loop tests**

Cover these exact cases in tests/test_model_executor.py:
- first turn returns final_report: one step, zero tools, completed report returned;
- search -> read -> final_report: three model turns and two tool calls;
- tests.run -> final_report: governed test result is appended to the next request;
- max_steps=1 blocks the second model turn before transport.send;
- malformed JSON emits protocol.failed once and does not retry;
- ModelTransportError emits provider.failed once and does not retry;
- known but ungranted tests.run reaches ToolDispatcher and is permission-denied;
- transport receives prior assistant envelope and tool-result message on the next turn;
- executor info reports fake/fixture-model in deterministic tests.

Representative expected loop:

~~~python
responses = (
    '{"type":"tool_request","tool":"repository.search","arguments":{"query":"timeout"}}',
    '{"type":"tool_request","tool":"repository.read","arguments":{"path":"settings.py"}}',
    '{"type":"final_report","report":{"status":"completed","findings":[{"id":"F-1","claim":"missing conversion"}],"evidence":[{"finding_id":"F-1","source":"settings.py","observation":"milliseconds copied directly"}],"alternative_hypotheses":[],"uncertainties":[],"recommended_next_action":["convert at loader boundary"]}}',
)
~~~

- [ ] **Step 3: Run executor tests and confirm RED**

~~~powershell
python -m pytest tests/test_model_executor.py -q
~~~

Expected: FAIL because ModelExecutor does not exist.

- [ ] **Step 4: Implement the iterative loop**

Create src/bsap/model_executor.py with this control flow:

~~~python
class ModelExecutor:
    def __init__(
        self,
        *,
        transport: ModelTransport,
        prompt_builder: PromptBuilder | None = None,
        action_parser: ActionParser | None = None,
    ) -> None:
        self._transport = transport
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._action_parser = action_parser or ActionParser()

    @property
    def info(self) -> ExecutorInfo:
        return ExecutorInfo(
            type="model",
            version="0.2",
            transport=self._transport.transport_name,
            model=self._transport.model_name,
        )

    def execute(self, prepared, tools, emit):
        system_prompt = self._prompt_builder.system_prompt(prepared)
        messages = list(self._prompt_builder.initial_messages(prepared))
        turn = 0

        while True:
            tools.consume_step()
            turn += 1
            emit("model.requested", {"turn": turn})

            try:
                response = self._transport.send(
                    ModelRequest(
                        system_prompt=system_prompt,
                        messages=tuple(messages),
                    )
                )
            except ModelTransportError as exc:
                emit(
                    "provider.failed",
                    {"turn": turn, "category": exc.category.value},
                )
                raise

            emit(
                "model.completed",
                {"turn": turn, "response_chars": len(response.text)},
            )
            messages.append(ModelMessage(role="assistant", content=response.text))

            try:
                action = ActionParser().parse(
                    response.text,
                    agent_id=prepared.agent_id,
                )
            except ModelProtocolError as exc:
                emit(
                    "protocol.failed",
                    {"turn": turn, "code": exc.code},
                )
                raise

            if isinstance(action, ToolRequestAction):
                result = tools.call(action.tool, action.arguments)
                messages.append(
                    self._prompt_builder.tool_result_message(
                        action.tool,
                        action.arguments,
                        result,
                    )
                )
                continue

            emit("report.started", {})
            emit(
                "report.completed",
                {"finding_count": len(action.report.findings)},
            )
            return action.report
~~~

Do not catch ToolDispatcher failures here; existing manager semantics remain responsible for permission, context, budget, and test failures.

Do not retry transport.send or parsing.

- [ ] **Step 5: Run executor, sandbox, and deterministic-executor regression tests**

~~~powershell
python -m pytest tests/test_model_executor.py tests/test_executor_and_manager.py tests/test_sandbox.py -q
~~~

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add src/bsap/model_executor.py tests/test_model_executor.py
git commit -m "feat: add bounded BSAP model executor"
~~~

---

### Task 5: Real allowlisted host-side tests without shell access

**Files:**
- Create: src/bsap/test_runner.py
- Modify: src/bsap/sandbox.py
- Test: tests/test_test_runner.py
- Test: tests/test_sandbox.py

**Interfaces:**
- Produces: ApprovedTest(name: str, command: tuple[str, ...], cwd: Path, timeout_seconds: float = 30.0, max_output_chars: int = 4000)
- Produces: TestRunTimeout
- Produces: AllowlistedTestRunner(tests: tuple[ApprovedTest, ...]).run(name: str) -> Mapping[str, object]
- Produces: HostTestWorkspace, which preserves InMemoryWorkspace read/search behavior and delegates run_test to AllowlistedTestRunner

- [ ] **Step 1: Write real subprocess tests**

Create tests/test_test_runner.py using tmp_path and sys.executable.

Cover:
- approved command returns exit_code=0, passed=True, timed_out=False;
- failing approved command returns its nonzero code and passed=False without raising;
- stdout/stderr are truncated to max_output_chars with a visible truncation suffix;
- unregistered identifier raises KeyError before any subprocess starts;
- timeout raises TestRunTimeout;
- the command is a tuple and subprocess.run is called with shell=False;
- HostTestWorkspace can read only frozen files while running approved tests.

Representative tests:

~~~python
import sys
from pathlib import Path

import pytest

from bsap.test_runner import (
    AllowlistedTestRunner,
    ApprovedTest,
    TestRunTimeout,
)


def test_approved_test_runs_without_shell(tmp_path: Path) -> None:
    runner = AllowlistedTestRunner(
        tests=(
            ApprovedTest(
                name="unit",
                command=(sys.executable, "-c", "print('PASS-MARKER')"),
                cwd=tmp_path,
            ),
        )
    )
    result = runner.run("unit")
    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "PASS-MARKER"
    assert result["timed_out"] is False


def test_unknown_identifier_is_denied(tmp_path: Path) -> None:
    runner = AllowlistedTestRunner(tests=())
    with pytest.raises(KeyError):
        runner.run("invented-command")
~~~

For timeout, execute a preapproved Python command that sleeps longer than a 0.05-second test timeout.

- [ ] **Step 2: Run tests and confirm RED**

~~~powershell
python -m pytest tests/test_test_runner.py tests/test_sandbox.py -q
~~~

Expected: FAIL because the runner/workspace do not exist.

- [ ] **Step 3: Implement the runner**

Use subprocess.run with:
- args=spec.command
- cwd=spec.cwd
- shell=False
- capture_output=True
- text=True
- check=False
- timeout=spec.timeout_seconds
- an environment copied from os.environ with PYTHONDONTWRITEBYTECODE=1

Normal results return:

~~~python
{
    "name": name,
    "passed": completed.returncode == 0,
    "exit_code": completed.returncode,
    "stdout": bounded_stdout,
    "stderr": bounded_stderr,
    "timed_out": False,
}
~~~

On subprocess.TimeoutExpired raise TestRunTimeout with only the approved test identifier in the safe message; do not expose raw command text in the child-facing exception.

- [ ] **Step 4: Integrate HostTestWorkspace and tool failure events**

In sandbox.py:
- keep InMemoryWorkspace unchanged for EXEC-01;
- add HostTestWorkspace as a subclass that accepts an AllowlistedTestRunner and overrides run_test;
- when tests.run references an unknown identifier, emit permission.denied and raise PermissionDenied("Test is not allowlisted: <name>");
- translate TestRunTimeout into ToolTimeout after emitting tool.failed with {"name": "tests.run", "reason": "timeout"};
- preserve budget consumption before the test begins.

Add to tests/test_sandbox.py:
- unknown tests.run produces permission.denied;
- timed-out tests.run produces tool.failed and raises ToolTimeout;
- no filesystem.write, network.request, or subagent.spawn path is introduced.

- [ ] **Step 5: Run sandbox/test-runner/failure-injection tests**

~~~powershell
python -m pytest tests/test_test_runner.py tests/test_sandbox.py tests/test_failure_injection.py -q
~~~

Expected: PASS.

- [ ] **Step 6: Commit**

~~~powershell
git add src/bsap/test_runner.py src/bsap/sandbox.py tests/test_test_runner.py tests/test_sandbox.py
git commit -m "feat: add allowlisted BSAP test execution"
~~~

---

### Task 6: Explicit model/provider failure classification in the manager

**Files:**
- Modify: src/bsap/manager.py
- Modify: tests/test_failure_injection.py
- Modify: tests/test_executor_and_manager.py

**Interfaces:**
- Consumes: ModelProtocolError
- Consumes: ModelTransportError
- Preserves: existing COMPLETED, FAILED, CANCELLED, OUTCOME_UNKNOWN behavior

- [ ] **Step 1: Write failing classification tests**

Add executors that raise ModelTransportError and ModelProtocolError before any tool starts.

Assert:
- each results in TerminalOutcome.FAILED;
- agent.failed contains reason=provider_failure plus category for transport errors;
- agent.failed contains reason=protocol_failure plus code for protocol errors;
- exception message/raw provider payload is absent from events;
- the active child slot is released afterward;
- event-store failure still wins as OUTCOME_UNKNOWN;
- existing unknown-effect-after-tool-start behavior remains OUTCOME_UNKNOWN.

Representative assertion:

~~~python
failed_event = next(event for event in result.events if event.kind == "agent.failed")
assert failed_event.payload == {
    "classification": "FAILED",
    "reason": "provider_failure",
    "category": "timeout",
}
~~~

- [ ] **Step 2: Run failure tests and confirm RED**

~~~powershell
python -m pytest tests/test_failure_injection.py tests/test_executor_and_manager.py -q
~~~

Expected: new classification tests FAIL because manager currently treats these as generic RuntimeError.

- [ ] **Step 3: Add narrow catches before the generic RuntimeError branch**

Implement:
- except ModelTransportError: transition FAILED; emit classification/reason/category.
- except ModelProtocolError: transition FAILED; emit classification/reason/code.

Do not add a broad Exception catch. Do not change EventStoreFailure handling. Do not include str(exc) in events.

- [ ] **Step 4: Run the complete manager/failure suite**

~~~powershell
python -m pytest tests/test_failure_injection.py tests/test_executor_and_manager.py tests/test_lifecycle_and_events.py -q
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add src/bsap/manager.py tests/test_failure_injection.py tests/test_executor_and_manager.py
git commit -m "feat: classify BSAP model execution failures"
~~~

---

### Task 7: Byte-MCP NVIDIA live transport with a schema gate

**Files:**
- Create: src/bsap/byte_mcp_transport.py
- Create: tests/test_byte_mcp_transport.py
- Modify: pyproject.toml

**Interfaces:**
- Produces: NvidiaQueryInvoker protocol with invoke(prompt: str, model: str, system_prompt: str) -> str
- Produces: ByteMCPNvidiaTransport(invoker: NvidiaQueryInvoker, model_alias: str = "lightning")
- Produces: StreamableHttpNvidiaQueryInvoker(mcp_url: str)
- Uses exactly one nvidia_query tool call for each ModelTransport.send invocation
- Uses no retry/fallback/model substitution

- [ ] **Step 1: Add the optional MCP dependency**

Add:

~~~toml
[project.optional-dependencies]
dev = ["pytest>=9", "ruff>=0.16"]
nvidia = ["mcp==1.28.1"]
~~~

Do not make MCP a core runtime dependency; deterministic BSAP remains installable without it.

- [ ] **Step 2: Write fake-invoker transport tests**

Create tests/test_byte_mcp_transport.py with a fake invoker that records calls.

Assert:
- transport_name == "byte-mcp-nvidia";
- model_name == "lightning";
- one send causes exactly one invoker call;
- model is exactly "lightning";
- system_prompt is passed separately;
- conversation messages are rendered into a deterministic prompt;
- invoker exceptions already normalized as ModelTransportError propagate with no retry.

Representative fake:

~~~python
class RecordingInvoker:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls = []

    def invoke(self, *, prompt: str, model: str, system_prompt: str) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "system_prompt": system_prompt,
            }
        )
        return self.result
~~~

- [ ] **Step 3: Implement ByteMCPNvidiaTransport**

Render ModelRequest.messages deterministically as a canonical JSON array of role/content objects and prefix only a short instruction that this is the conversation to continue. Do not reinterpret model JSON in the transport; return the tool's model text as ModelResponse.text for ActionParser.

ByteMCPNvidiaTransport.send must contain no retry loop.

- [ ] **Step 4: Implement StreamableHttpNvidiaQueryInvoker with runtime schema validation**

Use the MCP 1.28.1 client API:

~~~python
async with streamable_http_client(self._mcp_url) as (
    read_stream,
    write_stream,
    _,
):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools = await session.list_tools()
        ...
        result = await session.call_tool(
            "nvidia_query",
            arguments={
                "prompt": prompt,
                "model": model,
                "system_prompt": system_prompt,
            },
        )
~~~

Before call_tool:
- find exactly one tool named nvidia_query;
- inspect its inputSchema;
- require properties prompt, model, and system_prompt;
- if absent, raise ModelTransportError(CONTRACT_MISMATCH, "Byte-MCP nvidia_query schema does not match EXEC-02");
- do not call the provider after a schema mismatch.

Normalize:
- connection/transport failure -> TRANSPORT_FAILURE;
- timeout -> TIMEOUT;
- MCP tool result with isError=true -> UNEXPECTED_PROVIDER_FAILURE;
- tool result that cannot yield exactly one model response string -> MALFORMED_RESPONSE.

For successful output extraction, accept a single string from structuredContent under response, result, text, or content; otherwise accept exactly one MCP TextContent block. If more than one candidate string exists, treat it as malformed rather than guessing.

Do not log or embed credential material or raw provider exceptions in ModelTransportError safe messages.

Use asyncio.run for the synchronous invoke method. If invoke is called while an asyncio loop is already running in the same thread, raise TRANSPORT_FAILURE with a safe message rather than nesting event loops.

- [ ] **Step 5: Unit-test schema and response normalization without network access**

Factor schema validation and successful-text extraction into private pure helpers that accept ordinary mappings/sequences so tests do not require a running Byte-MCP instance.

Cover:
- expected prompt/model/system_prompt schema accepted;
- missing nvidia_query rejected;
- missing required property rejected before call;
- one structured response string accepted;
- one TextContent-equivalent string accepted through a small fake object;
- multiple candidate strings rejected;
- isError mapped to normalized provider failure;
- no retry count exceeds one.

- [ ] **Step 6: Install the live extra and run deterministic tests**

~~~powershell
python -m pip install -e ".[dev,nvidia]"
python -m pytest tests/test_byte_mcp_transport.py tests/test_model_transport.py -q
~~~

Expected: PASS.

- [ ] **Step 7: Perform a no-provider schema probe against the live Byte-MCP runtime**

With Byte-MCP running at its configured local Streamable HTTP URL, call list_tools only and assert:
- nvidia_query exists;
- its input schema contains prompt, model, system_prompt;
- the model argument remains present as a string-capable input; the live canary, not the schema probe, proves that the configured lightning alias is accepted.

This step must not invoke nvidia_query. If the schema does not match, stop EXEC-02 integration work and update the transport contract deliberately; do not guess or bypass the gate.

- [ ] **Step 8: Commit**

~~~powershell
git add pyproject.toml src/bsap/byte_mcp_transport.py tests/test_byte_mcp_transport.py
git commit -m "feat: add Byte-MCP NVIDIA model transport"
~~~

---

### Task 8: Deterministic EXEC-02 end-to-end path, live canary, and failure documentation

**Files:**
- Create: tests/test_exec02_end_to_end.py
- Create: tests/fixtures/exec02_canary/settings.py
- Create: tests/fixtures/exec02_canary/client.py
- Create: tests/fixtures/exec02_canary/check_timeout.py
- Create: src/bsap/live_canary.py
- Create: docs/EXEC02-LIVE-CANARY.md
- Modify: README.md
- Modify: FAILURE_MAP.md

**Interfaces:**
- Produces: run_live_canary(transport: ModelTransport) -> tuple[SubAgentManager, ExecutionResult]
- Uses: HostTestWorkspace, AllowlistedTestRunner, ModelExecutor
- Leaves parent disposition unset until Byte evaluates the returned report

- [ ] **Step 1: Add the deterministic full-stack EXEC-02 test**

Create tests/test_exec02_end_to_end.py using FakeModelTransport with:
1. repository.search for timeout;
2. repository.read of settings.py;
3. tests.run of timeout-conversion;
4. final_report.

Assert:
- terminal outcome COMPLETED;
- final state TERMINATED;
- report has linked evidence;
- executor receipt type/model/transport are populated;
- exact event sequence contains model.requested/model.completed and governed tool events;
- no permission.denied event appears;
- parent disposition is None immediately after completion;
- recording a ParentDisposition afterward does not change the child terminal outcome.

- [ ] **Step 2: Add the live canary fixture**

tests/fixtures/exec02_canary/settings.py:

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class HttpSettings:
    request_timeout_seconds: int


def load_http_settings(raw: dict[str, str]) -> HttpSettings:
    return HttpSettings(
        request_timeout_seconds=int(raw["request_timeout_ms"]),
    )
~~~

tests/fixtures/exec02_canary/client.py:

~~~python
from settings import HttpSettings


def build_request_options(settings: HttpSettings) -> dict[str, int]:
    return {"timeout": settings.request_timeout_seconds}
~~~

tests/fixtures/exec02_canary/check_timeout.py:

~~~python
from client import build_request_options
from settings import load_http_settings


settings = load_http_settings({"request_timeout_ms": "5000"})
options = build_request_options(settings)

if options["timeout"] != 5:
    print(f"FAIL expected timeout=5 seconds, got {options['timeout']}")
    raise SystemExit(1)

print("PASS")
~~~

The defect is intentional and remains confined to the canary fixture.

- [ ] **Step 3: Implement run_live_canary**

The harness must:
- read only settings.py and client.py into the frozen workspace;
- register only timeout-conversion -> (sys.executable, check_timeout.py);
- prepare permissions filesystem_read=True, tests_run=True and all other permissions false;
- use Budget(max_steps=6, max_tool_calls=4);
- use a completion contract requiring findings, evidence, alternative_hypotheses, uncertainties, recommended_next_action;
- state the objective as diagnosing why 5000 milliseconds reaches the client as 5000 seconds;
- execute through ModelExecutor;
- return the manager and result;
- never auto-create ParentDisposition.

Provide a main entry point that constructs StreamableHttpNvidiaQueryInvoker from BYTE_MCP_URL, defaulting to http://127.0.0.1:8000/mcp, wraps it in ByteMCPNvidiaTransport(model_alias="lightning"), runs the canary, and prints only:
- agent_id;
- terminal_outcome;
- finding IDs and claims;
- evidence;
- uncertainties;
- recommended_next_action;
- receipt executor provenance;
- receipt hashes.

If the child outcome is COMPLETED, the CLI must then print PARENT_DISPOSITION_REQUIRED and remain in the same process waiting for exactly one JSON line on stdin with this schema:

~~~json
{
  "result": "accepted",
  "accepted_findings": ["F-1"],
  "rejected_findings": [],
  "rationale": "Evidence supports the loader-boundary diagnosis."
}
~~~

Validate result against ParentDispositionResult, require accepted/rejected finding IDs to be subsets of the actual report finding IDs, construct ParentDisposition, call manager.record_parent_disposition, print only the recorded disposition result, and exit. Invalid disposition JSON exits nonzero without changing the child terminal outcome.

Do not print raw hidden model turns, credentials, or raw provider errors.

- [ ] **Step 4: Document all new failure surfaces before live execution**

Extend FAILURE_MAP.md with separate sections for:
- Byte-MCP/provider unavailable;
- provider timeout;
- Byte-MCP nvidia_query schema drift;
- malformed model JSON;
- unknown envelope/tool/argument schema;
- provider success but invalid BSAP report;
- unauthorized tool request;
- context escape attempt;
- model step-budget exhaustion;
- tool-call budget exhaustion;
- unknown/unapproved test identifier;
- approved test timeout;
- approved test command misconfiguration;
- bounded-output truncation;
- model/provider failure after a governed read-only operation;
- audit/event-store loss during model execution.

For every section include observable symptom, likely causes, first diagnostics, propagation, safe recovery, data/state risk, do-not warning, and exact related test names.

State explicitly that a new provider attempt is a new BSAP execution identity and that automatic retry/fallback/substitution is forbidden.

- [ ] **Step 5: Update README**

Change current status to EXEC-02 implemented only after the deterministic suite is green. Document:
- deterministic EXEC-01 remains available;
- EXEC-02 adds a model-backed read-only investigator;
- core install stays provider-neutral;
- live NVIDIA support uses the nvidia optional extra and existing Byte-MCP credentials;
- exact deterministic verification commands;
- exact live canary command.

- [ ] **Step 6: Run the entire deterministic verification suite before touching the provider**

~~~powershell
python -m ruff check .
python -m pytest -q
$env:PYTHONPATH = "src"
python -W error -m bsap.demo
python -m compileall -q src tests
git diff --check
~~~

Expected:
- Ruff: clean.
- Full pytest suite: all tests pass.
- EXEC-01 deterministic demo: completes with warnings treated as errors.
- compileall: clean.
- git diff --check: clean.

If any deterministic gate fails, do not make a live NVIDIA request.

- [ ] **Step 7: Run exactly one live EXEC-02 Lightning canary**

Preconditions:
- live Byte-MCP schema probe from Task 7 passed;
- Lightning is the selected governed alias;
- no retry/fallback/model substitution is configured;
- deterministic suite is green.

Run:

~~~powershell
$env:PYTHONPATH = "src"
python -W error -m bsap.live_canary
~~~

Acceptance criteria:
- exactly one BSAP child identity is created;
- each model turn invokes nvidia_query at most once;
- Lightning independently requests one or more approved tools rather than receiving all evidence prepackaged;
- no write/network/spawn child capability is exposed;
- final terminal outcome is COMPLETED;
- final BsapReport satisfies the completion contract and links every finding to evidence;
- receipt identifies type=model, transport=byte-mcp-nvidia, model=lightning;
- no hidden provider retry occurs.

If provider failure occurs, record the FAILED execution and stop. Do not rerun under the same identity. A subsequent attempt requires an explicit new BSAP execution.

- [ ] **Step 8: Perform Byte parent disposition review**

Leave the live-canary process open at PARENT_DISPOSITION_REQUIRED. Copy the printed evidence-backed report and observable receipt data to Byte. Byte evaluates only that material and returns one disposition JSON object using one existing ParentDispositionResult:
- accepted;
- partially_accepted;
- rejected;
- requires_further_investigation.

Paste Byte's disposition JSON as the single stdin line to the still-running canary process. The CLI validates it and records it through SubAgentManager.record_parent_disposition before process exit. Confirm that the child terminal outcome remains COMPLETED regardless of parent disposition.

Do not make acceptance automatic based on keywords, the known fixture defect, or expected diagnosis.

- [ ] **Step 9: Record the live acceptance evidence**

Create docs/EXEC02-LIVE-CANARY.md containing:
- date/time of run;
- agent_id;
- model alias lightning;
- transport byte-mcp-nvidia;
- terminal outcome;
- ordered tool names requested;
- finding IDs;
- receipt request/context/policy/report SHA-256 values;
- parent disposition;
- confirmation that retries=0, fallback=0, substitution=0;
- any provider failure classification if the canary did not complete.

Do not include credentials, secrets, raw chain-of-thought, or unrelated conversation context.

- [ ] **Step 10: Re-run the full suite after documentation changes**

~~~powershell
python -m ruff check .
python -m pytest -q
$env:PYTHONPATH = "src"
python -W error -m bsap.demo
python -m compileall -q src tests
git diff --check
~~~

Expected: all gates clean.

- [ ] **Step 11: Commit the completed milestone**

~~~powershell
git add README.md FAILURE_MAP.md docs/EXEC02-LIVE-CANARY.md src tests pyproject.toml
git commit -m "feat: complete BSAP real read-only model worker"
~~~

---

## Final Verification Checklist

Before declaring BSAP-EXEC-02 complete, verify all of the following from fresh output:

- [ ] Existing EXEC-01 deterministic tests remain green.
- [ ] ModelTransport is provider-neutral.
- [ ] Strict JSON protocol rejects malformed/prose-wrapped/unknown envelopes.
- [ ] ModelExecutor autonomously loops through approved tools and is bounded by max_steps/max_tool_calls.
- [ ] No hidden transport retry exists.
- [ ] Frozen context still gates repository.read and repository.search.
- [ ] tests.run accepts only stable approved identifiers and never model-supplied shell text.
- [ ] Test subprocesses use shell=False, explicit cwd, timeout, and bounded stdout/stderr.
- [ ] Provider/protocol failures have distinct safe classifications.
- [ ] Receipt provenance identifies the model transport and model alias.
- [ ] Byte-MCP credentials remain outside the BSAP repository.
- [ ] Runtime nvidia_query schema is verified before the live provider call.
- [ ] The live Lightning canary performs a genuine investigation using governed tools.
- [ ] Byte records a separate parent disposition.
- [ ] FAILURE_MAP.md covers every significant EXEC-02 failure boundary.
- [ ] Ruff passes.
- [ ] Full pytest passes.
- [ ] EXEC-01 demo passes with warnings as errors.
- [ ] compileall passes.
- [ ] git diff --check passes.

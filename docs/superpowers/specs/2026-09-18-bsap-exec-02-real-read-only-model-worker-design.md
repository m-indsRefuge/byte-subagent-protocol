# BSAP-EXEC-02 — Real Read-Only Model Worker

## Status

Approved design for implementation planning.

## Objective

BSAP-EXEC-02 introduces the first genuinely independent model-backed BSAP child worker. The worker uses NVIDIA Nemotron 3.5 Lightning through the existing Byte-MCP NVIDIA infrastructure and can investigate software-engineering problems by autonomously choosing among explicitly approved repository-reading, repository-search, and test-execution tools. Byte remains the parent and final authority.

EXEC-02 extends EXEC-01 rather than replacing it. The existing lifecycle, one-child-at-a-time rule, frozen context, permissions, budgets, append-only events, terminal outcomes, report validation, receipts, and parent disposition remain authoritative. `ScriptedDeterministicExecutor` remains available as the deterministic reference implementation.

## Architecture

```text
Byte / parent
    |
    v
SubAgentManager
    |
    v
ModelExecutor
    |-- PromptBuilder
    |-- ActionParser
    |-- ToolDispatcher
    `-- ModelTransport
            |
            v
    ByteMCPNvidiaTransport
            |
            v
    Byte-MCP NVIDIA infrastructure
            |
            v
    Nemotron 3.5 Lightning
```

The provider/model selection is implementation configuration, not part of the core BSAP protocol. BSAP remains provider-neutral.

### Component responsibilities

`SubAgentManager` continues to own lifecycle, active-child enforcement, terminal outcome, receipt creation, and parent-disposition separation.

`ModelExecutor` implements the existing `Executor` contract and owns the iterative investigative loop. It constructs the initial child contract, sends model turns, parses structured responses, dispatches approved tool requests, returns structured tool results to the model, terminates the loop, and returns a `BsapReport`.

`PromptBuilder` deterministically constructs the child contract from the immutable `PreparedRequest`, including role, objective, delegation reason, frozen context summary, approved tools, tool argument schemas, budgets, completion contract, and strict response schema. It never includes Byte's full conversation history, personal memory, or unrelated project state.

`ActionParser` is a strict parsing boundary. It decodes model JSON, validates envelope type, validates required fields and tool arguments, rejects unknown message types and tools, and constructs typed internal actions or final reports. It never executes tools.

`ModelTransport` is a minimal provider-neutral interface equivalent to `send(model_request) -> model_response`. It knows nothing about repository tools, BSAP lifecycle, filesystem state, test registries, or parent disposition.

`ByteMCPNvidiaTransport` is the first live transport implementation. It uses the existing Byte-MCP NVIDIA provider infrastructure and the configured `lightning` model alias. It owns provider-specific transport and normalizes provider failures before they enter BSAP.

`ToolDispatcher` remains the authority over child tool access. A well-formed model request is not permission to execute; it must still pass BSAP permissions, frozen-context checks, allowlists, and budgets.

## Credential and network boundary

BSAP does not own NVIDIA credentials. Credentials remain in the existing Byte-MCP/provider infrastructure and are never exposed to the child model or stored in BSAP receipts/events.

The child continues to have `external_network = false`. Provider communication is trusted host infrastructure used to instantiate the worker; it is not a child capability. The child cannot browse the web, invoke NVIDIA directly, call arbitrary MCP tools, invoke another model, or make HTTP requests.

## Child permissions

The initial EXEC-02 capability envelope is:

```text
filesystem_read     true
tests_run           true
filesystem_write    false
external_network    false
spawn_subagents     false
```

Write-capable workers are explicitly outside EXEC-02 and remain reserved for a later milestone.

## Iterative investigative loop

EXEC-02 is a genuine bounded investigator rather than a one-shot reviewer. Within the frozen permission and budget envelope, Lightning may autonomously choose which approved investigative action to request next.

A typical flow is:

```text
objective
  -> model turn
  -> repository.search
  -> tool result
  -> model turn
  -> repository.read
  -> tool result
  -> model turn
  -> tests.run
  -> tool result
  -> model turn
  -> final BSAP report
```

The model never executes operations directly. Every tool request passes through `ToolDispatcher`.

## Strict child communication protocol

Every model response must be exactly one of two strict JSON envelope types.

### Tool request

```json
{
  "type": "tool_request",
  "tool": "repository.read",
  "arguments": {
    "path": "src/example.py"
  }
}
```

### Final report

```json
{
  "type": "final_report",
  "report": {
    "status": "completed",
    "findings": [],
    "evidence": [],
    "alternative_hypotheses": [],
    "uncertainties": [],
    "recommended_next_action": []
  }
}
```

There is no permissive extraction of JSON from surrounding prose. Malformed JSON, unknown envelope types, unknown tools, invalid arguments, unexpected structure, or malformed reports are protocol failures.

BSAP owns this protocol rather than depending on NVIDIA-native function calling, keeping the design portable to other models/providers.

## No chain-of-thought dependency

EXEC-02 does not request, persist, expose, or depend on hidden chain-of-thought. Observable events capture engineering-relevant actions and outcomes such as tool requests, tool starts/completions, permission denial, budget exhaustion, provider failure, protocol failure, report start/completion, and terminal outcome.

The useful worker output is the evidence-backed final report, not hidden reasoning traces.

## Frozen context

Before execution, Byte prepares an explicit `ContextManifest`. Only approved context enters the child session. The worker does not automatically receive Byte's full ChatGPT history, Nolan's personal memory, unrelated repositories, arbitrary filesystem contents, or other agents' state.

The assignment remains immutable after execution starts. If materially different context is required, the parent starts a new execution rather than silently expanding the child's world.

`repository.read` can read only approved files in the frozen context. `repository.search` searches only approved material. Attempts to cross the context boundary are denied explicitly.

## Real allowlisted test execution

EXEC-02 upgrades `tests.run` from EXEC-01's preloaded deterministic result mechanism to support real host-side test execution without exposing shell access to the model.

Byte prepares an explicit mapping from stable test identifiers to predefined host commands. The model can request only an identifier, for example:

```json
{
  "type": "tool_request",
  "tool": "tests.run",
  "arguments": {
    "name": "test_failure_case"
  }
}
```

The host validates the identifier, verifies `tests_run = true`, checks remaining budget, resolves the predefined command, executes it, captures bounded output, and returns a structured result.

The child cannot provide command text and therefore cannot request arbitrary `pytest`, Python, PowerShell, Bash, CMD, package-manager, or shell commands.

Test results return only bounded structured data such as approved identifier, pass/fail status, exit code, bounded stdout/stderr, and timeout status. Output limits prevent unbounded logs from consuming context or event storage.

## Session and retry semantics

One BSAP child execution may contain multiple model turns; those turns collectively form a single bounded model session.

There are no hidden provider retries. A provider failure ends the current BSAP execution according to its classified failure semantics. If Byte elects to retry the investigation, the retry receives a new BSAP execution identity.

Tool results from earlier turns remain available only within that child's bounded conversation state.

## Budget semantics

The existing `Budget` remains authoritative.

Each investigative model turn consumes one step. Governed tool operations consume tool-call budget according to the existing dispatcher rules. The model cannot increase either budget.

The loop must terminate through one of: valid final report, step-budget exhaustion, tool-call-budget exhaustion, provider failure, protocol/schema failure, permission/context violation, test timeout, supported explicit cancellation, or another classified execution failure.

EXEC-02 does not add token or wall-clock budget dimensions unless implementation evidence demonstrates they are necessary.

## Failure classification

Provider failures are normalized at the transport boundary into explicit categories such as unavailable, timeout, rejected request, malformed provider response, transport failure, and unexpected provider failure. Diagnostics must not leak secrets.

Protocol failures are distinct from provider failures. Examples include invalid JSON, unknown envelope type, unknown tool, invalid arguments, malformed final report, and completion-contract violation.

This distinction is required because provider unavailability and invalid model behavior have different causes and recovery paths.

## Terminal outcome and parent authority

The existing terminal outcomes remain authoritative:

```text
COMPLETED
FAILED
CANCELLED
OUTCOME_UNKNOWN
```

A valid child report does not imply that Byte accepts its findings. `COMPLETED` means only that the child successfully completed its BSAP contract.

Byte independently records one of the existing parent dispositions:

```text
accepted
partially_accepted
rejected
requires_further_investigation
```

The child cannot approve its own findings.

## Receipts and provenance

EXEC-02 continues to produce deterministic BSAP receipts for protocol-relevant artifacts. The receipt identifies the model executor/transport sufficiently to establish provenance without including secrets.

The event stream remains append-only and ordered. Intermediate model text is not used as a hidden reasoning log; the audit record focuses on governed actions, failures, final report, and externally meaningful outcomes.

## Testing strategy

Most EXEC-02 tests do not call NVIDIA. A `FakeModelTransport` feeds predetermined model responses into `ModelExecutor` so the control plane remains deterministic.

Deterministic coverage includes:

- one-tool investigation;
- multi-tool investigation;
- final-report generation;
- malformed JSON;
- unauthorized/unknown tools;
- invalid arguments;
- context violations;
- real allowlisted test execution;
- test timeout;
- step and tool-call budget exhaustion;
- malformed final reports;
- provider failure normalization;
- multi-turn sequencing;
- event ordering;
- receipt generation;
- regression coverage for EXEC-01.

The live NVIDIA path is tested separately as an explicit integration canary.

## Live canary

After deterministic verification passes, EXEC-02 receives one deliberately small live Lightning canary with no retries.

The canary uses a tiny frozen repository context, a small search/read surface, optionally one approved test, and low step/tool-call budgets. It must require actual investigation rather than simple string echoing.

Success means Lightning independently chooses valid BSAP tools, receives governed evidence, and returns a valid evidence-backed `BsapReport`. Byte then independently evaluates that report through the existing parent-disposition mechanism.

That run constitutes the first genuine BSAP model-backed sub-agent execution.

## Failure-aware engineering

`FAILURE_MAP.md` is updated as part of EXEC-02. At minimum it documents provider unavailable, provider timeout, malformed model output, repeated invalid protocol responses, unauthorized tool request, context escape attempt, budget exhaustion, test timeout, test registry misconfiguration, report-validation failure, provider success with invalid BSAP report, uncertain execution state, and receipt/event failure.

EXEC-02 is not complete until these significant failure boundaries and their related tests are documented.

## Security invariants

The following must remain true throughout EXEC-02:

```text
The model cannot write files.
The model cannot execute arbitrary commands.
The model cannot access unrestricted repository contents.
The model cannot access Byte's memory.
The model cannot access Nolan's unrelated personal context.
The model cannot browse the network.
The model cannot invoke providers directly.
The model cannot spawn another agent.
The model cannot change its assignment.
The model cannot increase its permissions.
The model cannot increase its budget.
The model cannot declare its own findings accepted.
```

## Explicitly out of scope

EXEC-02 does not include filesystem writes, Git commits, child-controlled Git branches/worktrees, arbitrary shell execution, package installation, web access, multiple simultaneous children, recursive delegation, persistent child memory, self-modification, automatic retries, autonomous provider/model switching, background execution, or long-running asynchronous children.

Those capabilities require later milestones and separate threat-boundary review.

## Definition of done

BSAP-EXEC-02 is complete only when all of the following are true:

1. EXEC-01 tests remain green.
2. A provider-neutral `ModelTransport` exists.
3. `ModelExecutor` implements the existing `Executor` interface.
4. Strict JSON tool/report parsing is implemented.
5. The iterative investigative loop is bounded and tested.
6. Read/search operations remain frozen-context constrained.
7. Real allowlisted local test execution works without exposing shell access.
8. Fake-transport deterministic tests cover significant success and failure paths.
9. Provider failures are explicitly classified.
10. No hidden retry occurs.
11. `FAILURE_MAP.md` covers the new subsystem.
12. Ruff passes.
13. The full pytest suite passes.
14. Compile verification passes.
15. Diff hygiene passes.
16. A live Nemotron 3.5 Lightning canary successfully performs an independent bounded investigation and returns a valid evidence-backed BSAP report.
17. Byte independently evaluates the live report through the existing parent-disposition mechanism.

## Resulting system

After EXEC-02, Lightning is a real independent investigative worker, while BSAP—not the model provider—defines what the worker may know, request, execute, report, and influence.

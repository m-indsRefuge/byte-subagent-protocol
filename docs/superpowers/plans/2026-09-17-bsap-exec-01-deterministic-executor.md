# BSAP-EXEC-01 Deterministic Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest deterministic BSAP v0.1 runtime that can execute one bounded read-only child assignment end to end and prove the protocol's lifecycle, governance, observability, report validation, receipt integrity, and failure semantics before any model executor is introduced.

**Architecture:** Implement BSAP as a small Python 3.12 package with immutable protocol models, deterministic canonical hashing, an explicit lifecycle state machine, append-only event log, an in-memory read-only workspace/tool boundary, a scripted deterministic executor, report validation, receipt generation, and a single-active-child manager. The executor is backend-independent: the manager depends on an `Executor` protocol so a real independent model session can replace the deterministic executor without changing Byte's parent-facing contract.

**Tech Stack:** Python 3.12, standard-library runtime only (`dataclasses`, `enum`, `hashlib`, `json`, `typing`, `uuid`, `datetime`), pytest 9+, Ruff.

**Spec:** `BSAP_SPEC.md`

## Global Constraints

- Protocol version is exactly `BSAP 0.1`.
- Parent identity for v0.1 is `BYTE`.
- At most one child may be active at a time.
- Delegation depth is exactly one; recursive spawning is denied.
- Child execution is read-only.
- External network access is denied.
- Permissions are deny-by-default.
- Context is explicit and frozen before execution.
- Running assignments may not silently mutate.
- Execution budgets are enforced before an over-budget action occurs.
- Events are append-only and ordered by a 1-based sequence number.
- Retries are new execution identities; there are no hidden retries.
- A valid child report is required for `COMPLETED`.
- Child `COMPLETED` does not imply parent acceptance.
- Terminal outcomes are `COMPLETED`, `FAILED`, `CANCELLED`, and `OUTCOME_UNKNOWN`; resource cleanup is represented by lifecycle state `TERMINATED` while preserving the terminal outcome.
- Runtime code must not call model providers, external network services, or real shell commands in EXEC-01.
- Significant failure boundaries added by this milestone must be reflected in `FAILURE_MAP.md` with related tests.
- Do not add multiple children, writable workspaces, Git worktrees, recursive delegation, child-to-child communication, provider APIs, shared mutable memory, or dynamic permission escalation.

---

## File Structure

Create or modify exactly these implementation surfaces for EXEC-01:

- `pyproject.toml` — package metadata, Python floor, pytest and Ruff configuration.
- `src/bsap/__init__.py` — small public API export surface only.
- `src/bsap/models.py` — immutable protocol dataclasses and enums; no execution logic.
- `src/bsap/canonical.py` — deterministic canonical JSON conversion and SHA-256 hashing.
- `src/bsap/lifecycle.py` — lifecycle transition validation plus append-only event log.
- `src/bsap/sandbox.py` — explicit-context in-memory workspace, deny-by-default tool dispatcher, permission checks, and budget accounting.
- `src/bsap/reporting.py` — completion-contract and evidence validation.
- `src/bsap/receipt.py` — immutable receipt construction from frozen inputs and terminal outcome.
- `src/bsap/executor.py` — `Executor` protocol and scripted deterministic executor.
- `src/bsap/manager.py` — single-active-child orchestration, lifecycle handling, failure classification, and parent disposition recording.
- `src/bsap/demo.py` — controlled timeout-unit investigation demonstration; no external calls.
- `tests/test_models_and_hashing.py` — immutability and canonical hash tests.
- `tests/test_lifecycle_and_events.py` — legal/illegal transitions and append-only ordering.
- `tests/test_sandbox.py` — context isolation, denied capabilities, and budget enforcement.
- `tests/test_reporting.py` — report/completion-contract evidence rules.
- `tests/test_receipt.py` — receipt binding and hash-change tests.
- `tests/test_executor_and_manager.py` — executor abstraction, single-child governance, parent disposition, cancellation/failure semantics.
- `tests/test_failure_injection.py` — executor crash, tool timeout, event-store failure, malformed report, budget exhaustion, cancellation, and `OUTCOME_UNKNOWN`.
- `tests/test_end_to_end.py` — the canonical timeout-unit vertical slice.
- `README.md` — status and deterministic-demo commands after the harness works.
- `FAILURE_MAP.md` — add concrete runtime failure boundaries discovered during implementation.

The package should stay small. Do not introduce a database, asynchronous framework, web server, message queue, JSON-Schema runtime dependency, or provider SDK in this milestone.

---

### Task 1: Establish the Python package and immutable protocol contracts

**Files:**
- Create: `pyproject.toml`
- Create: `src/bsap/__init__.py`
- Create: `src/bsap/models.py`
- Create: `tests/test_models_and_hashing.py`
- Delete after replacement: `src/.gitkeep`
- Delete after replacement: `tests/.gitkeep`

**Interfaces:**
- Produces enums: `LifecycleState`, `TerminalOutcome`, `ParentDispositionResult`.
- Produces frozen dataclasses: `DelegationReason`, `PermissionSet`, `Budget`, `ContextManifest`, `CompletionContract`, `BsapRequest`, `PreparedRequest`, `Event`, `Finding`, `Evidence`, `AlternativeHypothesis`, `BsapReport`, `ParentDisposition`, `ExecutorInfo`, `Receipt`, `ExecutionResult`.
- Later tasks must import these types rather than redefining protocol fields.

- [ ] **Step 1: Add project configuration**

Create `pyproject.toml` with Python `>=3.12`, a `src` package layout, pytest test path `tests`, and Ruff targeting Python 3.12. Keep runtime dependencies empty; place pytest and Ruff in a development optional dependency group.

- [ ] **Step 2: Write failing immutability tests**

In `tests/test_models_and_hashing.py`, construct `Budget(max_steps=25, max_tool_calls=20)` and `PermissionSet(...)`, then assert assigning to a field raises `dataclasses.FrozenInstanceError`. Also assert `ContextManifest.files` is a tuple, not a mutable list.

- [ ] **Step 3: Run the tests and verify RED**

Run:

```powershell
python -m pytest tests/test_models_and_hashing.py -v
```

Expected: import failure because `bsap.models` does not exist yet.

- [ ] **Step 4: Implement the protocol models**

Use `@dataclass(frozen=True, slots=True)` for protocol values. Use `StrEnum` for states/outcomes. Minimum field contracts:

```python
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
```

Use tuples for every sequence carried by frozen models. `PreparedRequest` must include `request_sha256`, `context_manifest_sha256`, and `policy_sha256`; it must not hold a mutable request/context object.

`BsapReport` must include `agent_id`, `status`, `findings`, `evidence`, `alternative_hypotheses`, `uncertainties`, and `recommended_next_action`.

`ExecutionResult` must preserve both `terminal_outcome` and final lifecycle state `TERMINATED`, plus `events`, optional `report`, and `receipt`.

- [ ] **Step 5: Run the model tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_models_and_hashing.py -v
```

Expected: PASS for model construction and immutability tests that do not yet depend on canonical hashing.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml src/bsap tests/test_models_and_hashing.py
git commit -m "feat: define BSAP protocol models"
```

---

### Task 2: Add deterministic canonical serialization and artifact hashing

**Files:**
- Create: `src/bsap/canonical.py`
- Modify: `tests/test_models_and_hashing.py`

**Interfaces:**
- Produces: `to_canonical_data(value: object) -> object`
- Produces: `canonical_json(value: object) -> str`
- Produces: `sha256_hex(value: object) -> str`
- Consumes immutable dataclasses and enums from Task 1.

- [ ] **Step 1: Write failing hash tests**

Add tests proving dictionary key order does not affect `sha256_hex`, tuple order does affect it, enum values serialize as strings, and changing one byte of a context file name changes the manifest hash.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
python -m pytest tests/test_models_and_hashing.py -v
```

Expected: failure because canonical functions are missing.

- [ ] **Step 3: Implement canonical conversion and hashing**

`to_canonical_data` must recursively handle frozen dataclasses, `StrEnum`, mappings, tuples/lists, strings, numbers, booleans, and `None`. Reject unsupported types with `TypeError` rather than using `repr()`.

`canonical_json` must use:

```python
json.dumps(
    to_canonical_data(value),
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
```

`sha256_hex` returns `hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()`.

- [ ] **Step 4: Run tests and verify GREEN**

```powershell
python -m pytest tests/test_models_and_hashing.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add src/bsap/canonical.py tests/test_models_and_hashing.py
git commit -m "feat: add canonical BSAP hashing"
```

---

### Task 3: Implement lifecycle enforcement and append-only ordered events

**Files:**
- Create: `src/bsap/lifecycle.py`
- Create: `tests/test_lifecycle_and_events.py`

**Interfaces:**
- Produces: `InvalidTransitionError`.
- Produces: `Lifecycle(initial: LifecycleState = REQUESTED)` with `state`, `terminal_outcome`, and `transition(target)`.
- Produces: `EventLog(agent_id: str, clock: Callable[[], datetime])` with `emit(kind: str, payload: Mapping[str, object]) -> Event` and `events -> tuple[Event, ...]`.

- [ ] **Step 1: Write lifecycle tests**

Cover the successful chain `REQUESTED -> PREPARED -> RUNNING -> REPORTING -> COMPLETED -> TERMINATED`. Assert `terminal_outcome` remains `COMPLETED` after `TERMINATED`.

Add rejected transitions `REQUESTED -> COMPLETED`, `FAILED -> RUNNING`, and `TERMINATED -> RUNNING`.

- [ ] **Step 2: Write event-log tests**

Inject a fixed clock. Emit three events and assert sequences are exactly `(1, 2, 3)`, returned events are a tuple, and previously returned event objects cannot be mutated.

- [ ] **Step 3: Run tests and verify RED**

```powershell
python -m pytest tests/test_lifecycle_and_events.py -v
```

- [ ] **Step 4: Implement legal transitions**

Use an explicit transition map. The terminal states `COMPLETED`, `FAILED`, `CANCELLED`, and `OUTCOME_UNKNOWN` may transition only to `TERMINATED`. Preserve the terminal outcome separately.

- [ ] **Step 5: Implement append-only events**

Keep the backing list private. `events` returns `tuple(self._events)`. Sequence numbers increment only after a successful append.

- [ ] **Step 6: Run tests and verify GREEN**

```powershell
python -m pytest tests/test_lifecycle_and_events.py -v
```

- [ ] **Step 7: Commit**

```powershell
git add src/bsap/lifecycle.py tests/test_lifecycle_and_events.py
git commit -m "feat: enforce BSAP lifecycle and events"
```

---

### Task 4: Build the explicit-context read-only sandbox, permissions, and budgets

**Files:**
- Create: `src/bsap/sandbox.py`
- Create: `tests/test_sandbox.py`

**Interfaces:**
- Produces exceptions: `ContextAccessDenied`, `PermissionDenied`, `BudgetExceeded`, `ToolTimeout`, `OutcomeUnknownError`.
- Produces: `InMemoryWorkspace(files: Mapping[str, str], allowed_files: tuple[str, ...], test_results: Mapping[str, Mapping[str, object]] | None = None)`.
- Produces: `BudgetCounter(budget: Budget)` with `consume_step()` and `consume_tool_call()`.
- Produces: `ToolDispatcher(workspace, permissions, budget_counter, emit)` with `call(name: str, arguments: Mapping[str, object]) -> Mapping[str, object]`.

- [ ] **Step 1: Write context-isolation tests**

Create a workspace containing `allowed.py` and `secret.py` while the manifest allows only `allowed.py`. Assert `repository.read` succeeds for `allowed.py` and raises `ContextAccessDenied` for `secret.py`. Add a search test proving results never include excluded files.

- [ ] **Step 2: Write permission tests**

Assert `filesystem.write`, `network.request`, and `subagent.spawn` calls raise `PermissionDenied` before any side effect. Assert a `permission.denied` event is emitted.

- [ ] **Step 3: Write budget tests**

With `max_tool_calls=2`, allow two tool calls and assert the third raises `BudgetExceeded` before the underlying workspace method is called. Add equivalent coverage for `max_steps`.

- [ ] **Step 4: Run sandbox tests and verify RED**

```powershell
python -m pytest tests/test_sandbox.py -v
```

- [ ] **Step 5: Implement the read-only workspace**

Normalize paths using `PurePosixPath` string form for deterministic tests. Do not read the host filesystem in EXEC-01. Implement only `repository.read`, `repository.search`, and deterministic `tests.run` from preloaded `test_results`.

- [ ] **Step 6: Implement deny-by-default dispatch**

Unknown tools are denied. `repository.read` requires `filesystem_read`; `tests.run` requires `tests_run`. There is no implementation path for write, network, or spawn tools.

Emit `tool.requested`, then either `permission.denied`/`budget.exhausted` or `tool.started` and `tool.completed`. Budget checks occur before `tool.started`.

- [ ] **Step 7: Run tests and verify GREEN**

```powershell
python -m pytest tests/test_sandbox.py -v
```

- [ ] **Step 8: Commit**

```powershell
git add src/bsap/sandbox.py tests/test_sandbox.py
git commit -m "feat: add governed read-only BSAP sandbox"
```

---

### Task 5: Validate completion contracts and evidence-backed reports

**Files:**
- Create: `src/bsap/reporting.py`
- Create: `tests/test_reporting.py`

**Interfaces:**
- Produces: `ReportValidationError`.
- Produces: `validate_report(report: BsapReport, contract: CompletionContract) -> None`.

- [ ] **Step 1: Write report-validation tests**

Cover a valid investigator report containing all required fields. Add failures for missing required fields, empty findings when `findings` is required, empty evidence when `evidence` is required, a finding with no evidence referencing its `finding_id`, and a report whose `status` is not `completed`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest tests/test_reporting.py -v
```

- [ ] **Step 3: Implement validation**

Map completion-contract names exactly to `BsapReport` attributes. Reject unknown required field names. When findings are present, require at least one `Evidence` object for every finding ID. Do not invent evidence or repair malformed output.

- [ ] **Step 4: Run tests and verify GREEN**

```powershell
python -m pytest tests/test_reporting.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add src/bsap/reporting.py tests/test_reporting.py
git commit -m "feat: validate BSAP child reports"
```

---

### Task 6: Build immutable execution receipts

**Files:**
- Create: `src/bsap/receipt.py`
- Create: `tests/test_receipt.py`

**Interfaces:**
- Produces: `build_receipt(prepared: PreparedRequest, terminal_outcome: TerminalOutcome, events: tuple[Event, ...], report: BsapReport | None, executor_info: ExecutorInfo, created_at: datetime, started_at: datetime | None, finished_at: datetime) -> Receipt`.

- [ ] **Step 1: Write receipt tests**

Assert receipt fields include protocol/version, agent/parent IDs, request/context/policy hashes, executor identity, event count, terminal outcome, and report hash when a report exists. Assert `report_sha256 is None` when no report exists.

Assert changing one byte in a report changes only the report-derived hash, while timestamps do not alter request/context/policy hashes.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest tests/test_receipt.py -v
```

- [ ] **Step 3: Implement receipt construction**

Use hashes already frozen into `PreparedRequest`; compute only the report hash at receipt time. Never hash timestamps into deterministic artifact identities.

- [ ] **Step 4: Run tests and verify GREEN**

```powershell
python -m pytest tests/test_receipt.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add src/bsap/receipt.py tests/test_receipt.py
git commit -m "feat: add BSAP execution receipts"
```

---

### Task 7: Implement the executor abstraction and single-child manager

**Files:**
- Create: `src/bsap/executor.py`
- Create: `src/bsap/manager.py`
- Create: `tests/test_executor_and_manager.py`

**Interfaces:**
- Produces `Executor` protocol:

```python
class Executor(Protocol):
    @property
    def info(self) -> ExecutorInfo: ...

    def execute(
        self,
        prepared: PreparedRequest,
        tools: ToolDispatcher,
        emit: Callable[[str, Mapping[str, object]], Event],
    ) -> BsapReport: ...
```

- Produces `ScriptedDeterministicExecutor(actions: tuple[ToolCall, ...], report_builder: Callable[[tuple[Mapping[str, object], ...]], BsapReport])`.
- Produces `SubAgentManager(id_factory, clock)` with `prepare(...)`, `run(prepared, executor, workspace)`, `cancel(agent_id)`, and `record_parent_disposition(disposition)`.

- [ ] **Step 1: Write preparation tests**

Assert `prepare` creates a unique immutable agent ID, parent `BYTE`, hashes the request/context/policy, emits/records `REQUESTED -> PREPARED`, and rejects a second prepared/running child while one child is active.

- [ ] **Step 2: Write happy-path manager test**

Use a two-action scripted executor against the in-memory workspace. Assert the manager reaches terminal outcome `COMPLETED`, final lifecycle state `TERMINATED`, validates the report before completion, builds a receipt, and releases the active-child slot.

- [ ] **Step 3: Write parent-disposition independence test**

After a child is `COMPLETED` and terminated, assert there is no parent disposition until `record_parent_disposition` is called. Record `REJECTED` and verify child terminal outcome remains `COMPLETED`.

- [ ] **Step 4: Write retry/new-identity test**

Run one failing execution, then prepare another request and assert the second agent ID differs. There must be no internal automatic retry.

- [ ] **Step 5: Run focused tests and verify RED**

```powershell
python -m pytest tests/test_executor_and_manager.py -v
```

- [ ] **Step 6: Implement scripted deterministic execution**

`ScriptedDeterministicExecutor` executes only its declared `ToolCall` sequence through `ToolDispatcher`, captures results, and builds a report from those results. It must not access the workspace directly.

- [ ] **Step 7: Implement manager orchestration**

Flow:

```text
REQUESTED -> PREPARED -> RUNNING -> REPORTING -> COMPLETED -> TERMINATED
```

Classify known governed failures as `FAILED`; cancellation as `CANCELLED`; explicit `OutcomeUnknownError` as `OUTCOME_UNKNOWN`. Always preserve the terminal outcome after transitioning to `TERMINATED`.

Do not catch an error and silently restart execution.

- [ ] **Step 8: Run tests and verify GREEN**

```powershell
python -m pytest tests/test_executor_and_manager.py -v
```

- [ ] **Step 9: Commit**

```powershell
git add src/bsap/executor.py src/bsap/manager.py tests/test_executor_and_manager.py
git commit -m "feat: orchestrate deterministic BSAP children"
```

---

### Task 8: Add failure injection and explicit unknown-outcome coverage

**Files:**
- Create: `tests/test_failure_injection.py`
- Modify: `src/bsap/executor.py`
- Modify: `src/bsap/manager.py`
- Modify: `src/bsap/lifecycle.py` only if a test exposes a missing legal transition.

**Interfaces:**
- Test-only executor doubles may raise `RuntimeError`, `ToolTimeout`, `OutcomeUnknownError`, or an injected event-store exception.
- Production manager must classify outcomes without pretending certainty.

- [ ] **Step 1: Add executor-crash test**

Raise a known deterministic executor failure before any tool starts. Expected terminal outcome: `FAILED`, then `TERMINATED`.

- [ ] **Step 2: Add tool-timeout test**

Inject a deterministic `tests.run` timeout whose effects are known to be read-only. Expected terminal outcome: `FAILED` and a timeout event.

- [ ] **Step 3: Add budget-exhaustion test**

Script more tool calls than allowed. Assert the excess call never starts and execution becomes `FAILED`.

- [ ] **Step 4: Add malformed-report test**

Return an evidence-free report under a contract requiring evidence. Assert the child cannot become `COMPLETED`; outcome is `FAILED`.

- [ ] **Step 5: Add cancellation test**

Cancel an active execution through the manager's cancellation path. Expected terminal outcome: `CANCELLED`, then `TERMINATED`.

- [ ] **Step 6: Add unknown-outcome test**

Raise `OutcomeUnknownError` after a `tool.started` event but before a matching `tool.completed` event. Expected terminal outcome: `OUTCOME_UNKNOWN`, then `TERMINATED`. The receipt must preserve `OUTCOME_UNKNOWN`.

- [ ] **Step 7: Add event-store failure test**

Inject an event log whose append fails after execution has begun. Because BSAP can no longer prove a complete audit trail, assert `OUTCOME_UNKNOWN`; do not relabel it as ordinary `FAILED`.

- [ ] **Step 8: Run failure tests and verify GREEN**

```powershell
python -m pytest tests/test_failure_injection.py -v
```

- [ ] **Step 9: Commit**

```powershell
git add src/bsap tests/test_failure_injection.py
git commit -m "test: cover BSAP failure boundaries"
```

---

### Task 9: Prove the canonical timeout-unit investigation end to end

**Files:**
- Create: `src/bsap/demo.py`
- Create: `tests/test_end_to_end.py`
- Modify: `src/bsap/__init__.py`

**Interfaces:**
- Produces: `build_timeout_demo() -> tuple[SubAgentManager, PreparedRequest, ScriptedDeterministicExecutor, InMemoryWorkspace]`.
- Produces: `run_timeout_demo() -> tuple[ExecutionResult, ParentDisposition]`.

- [ ] **Step 1: Write the end-to-end test first**

Use an in-memory fixture containing:

```python
# settings.py
from dataclasses import dataclass

@dataclass(frozen=True)
class HttpSettings:
    request_timeout_seconds: int

def load_http_settings(raw: dict[str, str]) -> HttpSettings:
    return HttpSettings(
        request_timeout_seconds=int(raw["request_timeout_ms"]),
    )
```

and:

```python
# client.py
def build_request_options(settings):
    return {"timeout": settings.request_timeout_seconds}
```

Context also includes the observation `5000 milliseconds produced timeout=5000 seconds` and the external/internal unit contract.

The scripted executor must read only the two allowed files, search for the relevant timeout names, and construct a report with a finding that conversion is missing plus evidence tied to that finding. It must include the alternative hypothesis that the client converts later and reject it based on the supplied client source.

Assert:

- execution terminal outcome is `COMPLETED`;
- final lifecycle state is `TERMINATED`;
- no denied/excluded file was accessed;
- event sequences are contiguous starting at 1;
- the report passes validation;
- receipt hashes are populated;
- parent disposition is recorded separately as `ACCEPTED`.

- [ ] **Step 2: Run the end-to-end test and verify RED**

```powershell
python -m pytest tests/test_end_to_end.py -v
```

- [ ] **Step 3: Implement the deterministic demo**

Keep the demo entirely in memory. It may print events/report/receipt when invoked as `python -m bsap.demo`, but it must not call the network, shell, or host filesystem.

- [ ] **Step 4: Run the end-to-end test and verify GREEN**

```powershell
python -m pytest tests/test_end_to_end.py -v
```

- [ ] **Step 5: Run the demo manually**

```powershell
python -m bsap.demo
```

Expected output includes the agent ID, ordered event names, terminal outcome `COMPLETED`, report finding ID, receipt hashes, and parent disposition `ACCEPTED`.

- [ ] **Step 6: Commit**

```powershell
git add src/bsap/demo.py src/bsap/__init__.py tests/test_end_to_end.py
git commit -m "feat: demonstrate deterministic BSAP execution"
```

---

### Task 10: Close the milestone with documentation and full verification

**Files:**
- Modify: `FAILURE_MAP.md`
- Modify: `README.md`

**Interfaces:**
- Documentation must describe only behavior proven by the deterministic harness.
- Do not claim that a real model child exists in EXEC-01.

- [ ] **Step 1: Expand the failure map from implemented behavior**

Ensure concrete entries and related test names exist for context packaging, permission enforcement, budget exhaustion, executor interruption, event-store/audit loss, malformed reporting, parent over-trust, cancellation, and unknown outcome.

Each entry must include observable symptom, likely causes, first diagnostics, propagation, safe recovery, data/state risk where applicable, explicit `Do not` guidance, and related test file/function names.

- [ ] **Step 2: Update README status**

State that BSAP-EXEC-01 provides a deterministic protocol harness only. Document:

```powershell
python -m pytest
python -m bsap.demo
```

Also state that the next separate milestone is a genuine independent read-only model executor implementing the same `Executor` interface.

- [ ] **Step 3: Run Ruff**

```powershell
python -m ruff check .
```

Expected: no violations.

- [ ] **Step 4: Run the full test suite**

```powershell
python -m pytest -v
```

Expected: all tests pass with no network/provider calls.

- [ ] **Step 5: Run compile verification**

```powershell
python -m compileall -q src tests
```

Expected: exit code 0.

- [ ] **Step 6: Inspect the final diff for scope creep**

```powershell
git diff --check
git status --short
git diff -- BSAP_SPEC.md
```

Expected: `git diff --check` is clean, and `BSAP_SPEC.md` is unchanged unless a contradiction was discovered and explicitly approved before changing the spec.

- [ ] **Step 7: Commit milestone documentation**

```powershell
git add README.md FAILURE_MAP.md
git commit -m "docs: close BSAP EXEC-01 failure map"
```

- [ ] **Step 8: Final milestone verification**

Run again after the final commit:

```powershell
python -m ruff check .
python -m pytest -v
python -m compileall -q src tests
git status --short
```

Acceptance requires all three verification commands to succeed and the worktree to be clean.

---

## Spec Coverage Self-Review

The plan covers every EXEC-01 acceptance requirement from `BSAP_SPEC.md`:

- request/preparation/start/completion/termination: Tasks 1, 3, 7, 9;
- illegal transitions: Task 3;
- immutable prepared assignment: Tasks 1 and 7;
- explicit context isolation: Task 4;
- write/network/spawn denial: Task 4;
- budgets: Task 4 and failure injection in Task 8;
- ordered append-only events: Task 3;
- required report fields and evidence-backed completion: Task 5;
- independent parent disposition: Task 7 and Task 9;
- request/context/policy/report hashes: Tasks 2, 6, 7;
- immutable final receipt: Task 6;
- executor crash/tool timeout/event-store failure/malformed report/budget/cancellation: Task 8;
- `OUTCOME_UNKNOWN`: Tasks 3 and 8;
- canonical deterministic vertical slice: Task 9;
- living failure documentation and complete verification: Task 10.

No deferred BSAP capability is included in this plan.

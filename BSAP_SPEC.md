# Byte Sub-Agent Protocol (BSAP) v0.1 — Design Specification

**Status:** Approved design  
**Date:** 2026-09-17  
**Protocol version:** BSAP 0.1  
**System:** Recursive Agent Laboratory  
**Canonical role:** Governing specification for Byte's bounded sub-agent delegation protocol

## 1. Purpose

The Byte Sub-Agent Protocol (BSAP) defines how Byte may delegate a bounded engineering task to an isolated child worker while retaining responsibility for the parent task.

BSAP is not a general-purpose multi-agent framework. Its first purpose is to improve Byte's engineering workflow through controlled delegation for cases where independent investigation, verification, focused specialization, or bounded parallel work materially improves the outcome.

The protocol is backend-independent. Byte communicates with BSAP rather than directly with a specific model or provider. Executors may change without changing the parent-facing protocol.

## 2. Core principle

A sub-agent advises or performs bounded work. Byte remains the parent orchestrator and is responsible for deciding whether the child's output is accepted, rejected, or requires further investigation.

The protocol must make it possible to determine:

- why a child was created;
- who authorized it;
- what objective it received;
- what context it could access;
- what capabilities and permissions it had;
- what it actually did;
- what evidence it produced;
- what it concluded;
- how Byte disposed of the result; and
- what terminal outcome occurred.

If BSAP cannot establish these facts, the execution is not considered fully trustworthy.

## 3. Scope of BSAP v0.1

BSAP v0.1 supports:

- one parent: `BYTE`;
- at most one active child at a time;
- delegation depth of exactly one;
- read-only child execution;
- no external network access;
- no child-to-child communication;
- no recursive child spawning;
- explicit context packaging;
- deny-by-default permissions;
- deterministic execution budgets;
- append-only ordered events;
- structured evidence-backed reports;
- explicit parent disposition;
- immutable execution receipts;
- deterministic/mock executor as the first implementation;
- executor abstraction suitable for a later independent model-session executor.

BSAP v0.1 does not support:

- multiple concurrently active children;
- write access to project files;
- recursive delegation;
- child-created sub-agents;
- unrestricted shell or network access;
- hidden retries;
- mutation of an assignment after execution begins;
- implicit access to Byte's full conversation, memory, or unrelated project state;
- automatic promotion of child output into durable memory;
- provider-specific behavior in the protocol contract.

## 4. Architectural components

BSAP consists of five conceptual components.

### 4.1 Delegation Policy

The Delegation Policy determines whether a task should be delegated and records the reason.

Byte handles work directly by default. Delegation is appropriate only when an independent bounded worker is likely to improve correctness, coverage, speed, or verification enough to justify the added execution complexity.

### 4.2 Sub-Agent Manager

The Sub-Agent Manager owns:

- agent identity;
- lifecycle transitions;
- context validation and freezing;
- permission enforcement;
- budget enforcement;
- cancellation;
- terminal-state handling;
- receipt generation.

Byte does not directly manipulate child runtime state.

### 4.3 Executor Interface

The Executor Interface isolates BSAP from the implementation used to perform child work.

The first executor is deterministic/mock. A later executor may use an independent model session without changing Byte's contract with BSAP.

### 4.4 Event and Receipt Stream

Every execution produces an append-only ordered event stream and an immutable final receipt.

Events describe observable execution facts. Receipts bind the execution to its frozen request, context, policy, report, and terminal state.

### 4.5 Structured Report

A child returns a structured report rather than an unstructured conversational answer.

The report must satisfy the completion contract before the execution may be classified as `COMPLETED`.

## 5. Parent-child relationship

Each child has exactly one parent.

For BSAP v0.1:

```text
Nolan
  |
  v
BYTE
  |
  +-- BSA-000001
```

A child may recommend additional work but may not create another child.

If a child recommends another investigation, the recommendation is returned to Byte. Byte then decides whether to request a new child execution.

## 6. Agent identity

Every execution receives a unique immutable agent identifier.

Example:

```text
BSA-000001
```

A retry is always a new execution with a new identifier.

The same identifier must never represent two executions.

## 7. Delegation policy

Before creating a child, Byte evaluates five signals.

### 7.1 Independence

Would a separate line of reasoning reduce bias, tunnel vision, or premature convergence?

### 7.2 Parallelism

Can useful work proceed independently of Byte's current work?

### 7.3 Specialization

Would a narrow role with a smaller, purpose-built context improve performance?

### 7.4 Verification

Would an independent check materially increase confidence in a significant conclusion or implementation?

### 7.5 Cost and risk

Is the task substantial enough that delegation is worth the additional complexity, tool use, and execution cost?

### 7.6 Default decision

The default decision is `handle_parent`.

Delegation requires a positive justification.

### 7.7 Initial approved delegation classes

BSAP v0.1 is intended for:

- root-cause investigations with multiple credible hypotheses;
- adversarial review of a proposed fix or architecture;
- independent verification of significant implementation work;
- focused repository research with a cleanly bounded search surface;
- read-only test analysis;
- comparison of competing technical explanations;
- checking assumptions that may be wrong.

BSAP v0.1 should normally not be used for:

- trivial deterministic edits;
- formatting;
- obvious single-file fixes;
- routine commands;
- tasks requiring constant parent-child coordination;
- tasks whose complete context is already very small;
- work where delegation cost exceeds expected value.

### 7.8 Authorization

A child may be spawned only when one of the following is true:

1. Nolan explicitly requests a sub-agent.
2. Byte proposes delegation and Nolan approves.
3. A previously approved deterministic policy explicitly authorizes that class of delegation.

BSAP v0.1 does not grant broad autonomous spawning authority.

## 8. Delegation reason

Every `BSAP.REQUEST` must include a machine-readable delegation reason.

Example:

```yaml
delegation_reason:
  trigger: independent_verification
  rationale: >
    The proposed root cause depends on an assumption that has not
    been independently challenged.
  expected_value: >
    Detect alternative explanations before code modification.
```

Delegation without an explicit reason is invalid.

## 9. Roles

Roles are capability contracts, not personalities.

Initial role vocabulary may include:

- `investigator`
- `reviewer`
- `test-analyst`
- `researcher`

A role defines:

- its purpose;
- its default permission envelope;
- required report fields;
- expected observable artifacts.

BSAP must not depend on fictional character traits or persona role-play for independence.

The first real role implemented after the deterministic harness should be `investigator`.

## 10. Context isolation

A child receives an explicit Context Manifest.

The child must not implicitly inherit:

- Byte's full chat history;
- Byte's personal memory;
- unrelated project files;
- unrelated project state;
- unrelated semantic-memory records.

An example context manifest:

```yaml
context_manifest:
  files:
    - src/grounding.py
    - tests/test_grounding.py
  observations:
    - deterministic failing test output
  constraints:
    - investigation only
    - no code modification
  parent_summary:
    - Regression appeared after grounding refactor.
  excluded:
    - unrelated chat history
    - personal memory
    - unrelated project state
```

The manifest must be frozen before execution begins.

The protocol must allow an auditor to answer: "What information did this child possess when it reached its conclusion?"

## 11. Permissions

Permissions are deny-by-default.

BSAP v0.1 child permissions are:

```yaml
permissions:
  filesystem_read: allowed
  filesystem_write: denied
  tests_run: allowed
  external_network: denied
  spawn_subagents: denied
```

The exact tool surface exposed by an executor must be a subset of the permissions granted by the prepared request.

If permission enforcement cannot be established, execution must not start.

## 12. Budget

Every prepared request includes explicit execution limits.

Example:

```yaml
budget:
  max_steps: 25
  max_tool_calls: 20
```

An executor must not exceed the frozen budget.

Attempting a tool call after the tool-call budget is exhausted must not result in that tool call executing.

Budget exhaustion must be observable in the event stream.

## 13. Lifecycle state machine

BSAP v0.1 uses the following lifecycle states:

```text
REQUESTED
    |
    | validation succeeds
    v
PREPARED
    |
    | executor accepts
    v
RUNNING
    |
    +------------------+-------------------+
    |                  |                   |
    v                  v                   v
REPORTING            FAILED            CANCELLED
    |
    | report valid
    v
COMPLETED
```

Terminal execution outcomes are:

- `COMPLETED`
- `FAILED`
- `CANCELLED`
- `OUTCOME_UNKNOWN`

Resource cleanup follows terminal classification.

`TERMINATED` is recorded as the lifecycle cleanup state after resources are released. It does not replace the terminal execution outcome.

### 13.1 REQUESTED

Byte has decided that delegation is warranted and has issued a request.

Nothing has executed.

### 13.2 PREPARED

The request has passed validation.

The following are frozen:

- objective;
- delegation reason;
- role;
- context manifest;
- permissions;
- budget;
- completion contract;
- relevant policy version.

### 13.3 RUNNING

The executor has started child work.

Once `RUNNING` begins, the assignment must not silently mutate.

If the assignment needs to change, the parent must cancel the current execution and create a new execution identity.

### 13.4 REPORTING

Execution work has ended and the formal report is being validated.

### 13.5 COMPLETED

The child produced a report that satisfies the completion contract and the protocol has sufficient evidence to classify the execution outcome.

`COMPLETED` does not imply that Byte accepts the child's conclusions.

### 13.6 FAILED

The execution deterministically failed and BSAP can establish the failure classification.

### 13.7 CANCELLED

The parent or protocol cancelled the execution before normal completion.

### 13.8 OUTCOME_UNKNOWN

BSAP cannot establish with sufficient evidence what effects occurred during execution.

This state is not a synonym for unexpected error.

Example:

```text
tool command begins
runtime connection disappears
BSAP cannot prove whether the command completed
=> OUTCOME_UNKNOWN
```

### 13.9 TERMINATED

Execution resources have been released after terminal classification where safe.

## 14. Legal state transitions

The implementation must explicitly validate state transitions.

Valid examples include:

```text
REQUESTED -> PREPARED
PREPARED -> RUNNING
RUNNING -> REPORTING
REPORTING -> COMPLETED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> OUTCOME_UNKNOWN
COMPLETED -> TERMINATED
FAILED -> TERMINATED
CANCELLED -> TERMINATED
OUTCOME_UNKNOWN -> TERMINATED
```

Invalid examples include:

```text
REQUESTED -> COMPLETED
FAILED -> RUNNING
TERMINATED -> RUNNING
```

Illegal transitions must be rejected and recorded.

## 15. Protocol messages

BSAP v0.1 defines seven parent-facing protocol message types:

```text
BSAP.REQUEST
BSAP.PREPARE
BSAP.START
BSAP.EVENT
BSAP.REPORT
BSAP.CANCEL
BSAP.TERMINATE
```

These messages define the protocol boundary. Executor-specific details must not leak into the parent-facing contract.

## 16. BSAP.REQUEST

`BSAP.REQUEST` expresses Byte's intent to delegate.

Example:

```yaml
type: BSAP.REQUEST
protocol: BSAP
version: "0.1"

role: investigator

objective:
  Determine why test_grounding.py fails.

delegation_reason:
  trigger: independent_investigation
  rationale: >
    Multiple credible causes remain and an independent hypothesis
    search may reduce tunnel vision.
  expected_value: >
    Establish or reject the suspected root cause without modifying code.

context_requirements:
  - relevant source files
  - failing test
  - latest deterministic failure output

requested_capabilities:
  - repository.read
  - repository.search
  - tests.run

completion_contract:
  require:
    - findings
    - evidence
    - alternative_hypotheses
    - uncertainties
```

## 17. BSAP.PREPARE

`BSAP.PREPARE` represents a validated and frozen assignment.

The prepared form must include:

- agent ID;
- parent ID;
- objective;
- delegation reason;
- role;
- complete context manifest;
- effective permissions;
- effective budget;
- completion contract;
- protocol version;
- policy identity or policy hash.

The prepared request is immutable.

## 18. BSAP.START

`BSAP.START` starts execution of an already prepared request.

Starting an unprepared request is invalid.

## 19. BSAP.EVENT

`BSAP.EVENT` records observable execution activity.

Minimum event fields:

```yaml
type: BSAP.EVENT
agent_id: BSA-000001
sequence: 9
timestamp: 2026-09-17T20:34:12Z
kind: evidence.recorded
payload: {}
```

`sequence` is the authoritative ordering field.

Timestamps are informative but must not be relied upon as the sole source of event ordering.

## 20. Observable cognitive artifacts

BSAP does not attempt to expose private model chain-of-thought.

Instead, executors may emit explicit engineering artifacts such as:

- observation;
- hypothesis;
- evidence;
- decision;
- tool action;
- uncertainty;
- critique;
- finding.

Example:

```yaml
kind: hypothesis.recorded
payload:
  hypothesis_id: H-002
  statement: >
    The grounding regression may originate at the context
    normalization boundary.
  based_on:
    - E-003
  status: active
```

A later event may update that explicit artifact:

```yaml
kind: hypothesis.updated
payload:
  hypothesis_id: H-002
  status: rejected
  reason: >
    Regression reproduces before normalization occurs.
```

These artifacts are intended for scientific and engineering observability, not as substitutes for hidden internal reasoning.

## 21. Event stream

Events are append-only.

An execution may produce events such as:

```text
0001 agent.created
0002 context.validated
0003 agent.started
0004 observation.recorded
0005 tool.requested
0006 tool.started
0007 tool.completed
0008 hypothesis.recorded
0009 evidence.recorded
0010 report.started
0011 report.completed
0012 agent.completed
0013 agent.terminated
```

Previously emitted event payloads must not be silently rewritten.

Corrections must be represented by later events.

## 22. BSAP.REPORT

A report is the child's formal conclusion and must be validated independently from the event stream.

Minimum report shape for the first `investigator` role:

```yaml
type: BSAP.REPORT
agent_id: BSA-000001
status: completed

findings:
  - id: F-001
    claim: Configuration value is interpreted in the wrong unit.

evidence:
  - finding_id: F-001
    source: settings.py
    observation: >
      Loader copies milliseconds directly into a field documented
      as seconds.

alternative_hypotheses:
  - claim: HTTP client performs the conversion later.
    disposition: rejected
    basis: >
      Client consumes the settings value directly.

uncertainties: []

recommended_next_action:
  - Correct the conversion boundary and add regression coverage.
```

A report that does not satisfy the frozen completion contract must not produce `COMPLETED`.

## 23. Parent disposition

Byte must explicitly evaluate a completed report before using its conclusions.

The parent disposition records:

```yaml
parent_disposition:
  agent_id: BSA-000001
  result: accepted
  accepted_findings:
    - F-001
  rejected_findings: []
  rationale: >
    Evidence was independently reproducible from the supplied artifacts.
```

Permitted disposition categories for v0.1 are:

- `accepted`
- `partially_accepted`
- `rejected`
- `requires_further_investigation`

A completed child report is advisory until parent disposition occurs.

## 24. Retry semantics

BSAP v0.1 has no invisible retries.

If an execution fails and Byte wants another attempt:

```text
BSA-000001 => FAILED
BSA-000002 => REQUESTED
```

The second attempt must have a new execution identity and its own event stream and receipt.

## 25. Failure model

BSAP recognizes four failure boundaries.

### 25.1 Pre-execution failures

Examples:

- invalid request;
- invalid context manifest;
- permission contract cannot be enforced;
- unavailable executor;
- invalid completion contract.

These failures must occur before `RUNNING`.

### 25.2 Execution failures

Examples:

- tool failure;
- budget exhaustion;
- executor crash;
- timeout;
- prohibited action attempted.

### 25.3 Reporting failures

Examples:

- malformed report;
- missing required evidence;
- incomplete completion contract;
- contradictory report state;
- invalid report references.

### 25.4 Integration failures

Examples:

- Byte accepts an unsupported claim;
- child used stale context;
- report references evidence that was not available to the child;
- parent misinterprets child output.

Integration failures are parent-side failures and must not be mislabeled as successful child validation.

## 26. Fail-closed rules

BSAP v0.1 fails closed at governance boundaries.

If permissions cannot be established:

```text
do not run
```

If the Context Manifest cannot be validated:

```text
do not run
```

If the report does not satisfy the completion contract:

```text
do not classify as COMPLETED
```

If BSAP cannot determine whether execution effects occurred:

```text
classify as OUTCOME_UNKNOWN
```

## 27. Execution receipt

Every execution produces an immutable receipt.

Minimum receipt content:

```yaml
protocol: BSAP
version: "0.1"

agent_id: BSA-000001
parent_id: BYTE

request_sha256: "<sha256>"
context_manifest_sha256: "<sha256>"
policy_sha256: "<sha256>"

executor:
  type: deterministic
  version: "<executor-version>"

created_at: "<timestamp>"
started_at: "<timestamp>"
finished_at: "<timestamp>"

terminal_state: COMPLETED

event_count: 17
report_sha256: "<sha256>"
```

The receipt binds a report to its frozen execution inputs and outcome.

Future model executors may extend the receipt with fields such as:

```yaml
model:
  provider: "<provider>"
  model: "<model>"
  parameters: {}

usage:
  input_tokens: 0
  output_tokens: 0
  tool_calls: 0
```

These extensions must not alter the semantics of the v0.1 core receipt.

## 28. Hashing

Cryptographic hashes are used to detect mutation and bind execution artifacts.

The initial implementation uses SHA-256 for:

- prepared request;
- Context Manifest;
- applicable policy representation;
- final report.

Hash computation must use a deterministic canonical serialization.

Timestamps and other explicitly nondeterministic metadata must not be included in deterministic artifact hashes unless the specification for that artifact explicitly requires them.

## 29. First executor

The first implementation is a deterministic executor.

Its purpose is to validate:

- lifecycle;
- transition enforcement;
- request freezing;
- context isolation;
- permission enforcement;
- budgets;
- event ordering;
- report validation;
- parent disposition;
- receipt integrity;
- failure handling.

It is not intended to simulate general LLM intelligence.

The deterministic harness exists so that protocol defects can be distinguished from model/runtime behavior.

## 30. First real model executor

After the deterministic protocol harness is validated, the next milestone is a genuine independently executing model session.

The model executor must satisfy the same BSAP contract.

Byte must not need provider-specific logic to use it.

The first real model role is `investigator`, with:

- read-only permissions;
- no child delegation;
- explicit selected context;
- bounded tools;
- required claims and evidence;
- no code modification.

## 31. First end-to-end demonstration

The first deterministic demonstration uses a controlled engineering defect.

Example fixture:

```python
def load_timeout(raw):
    return int(raw["timeout_ms"])
```

Contract:

```text
external timeout value: milliseconds
internal timeout value: seconds
```

The child receives only the bounded fixture, its contract, and the deterministic failing observation.

Expected child conclusion:

- finding: unit conversion is missing;
- evidence: a millisecond value is copied directly into a seconds representation;
- alternative hypothesis: conversion occurs later;
- alternative disposition: rejected when the downstream consumer uses the value directly.

Byte then records an explicit parent disposition.

No source file is modified.

No external network or provider is called.

This demonstration must exercise:

```text
delegation assessment
-> request
-> context isolation
-> permission contract
-> prepared/frozen assignment
-> deterministic executor
-> event stream
-> structured reasoning artifacts
-> report validation
-> parent disposition
-> immutable receipt
-> termination
```

## 32. Testing strategy

### 32.1 Lifecycle tests

Test all legal transitions.

Test representative illegal transitions including:

```text
REQUESTED -> COMPLETED
FAILED -> RUNNING
TERMINATED -> RUNNING
```

Illegal transitions must be rejected deterministically.

### 32.2 Permission tests

A read-only worker attempting a write must:

- not perform the write;
- emit an observable permission-denied event;
- preserve governed execution state;
- transition according to the configured severity policy.

### 32.3 Context-isolation tests

Verify:

```text
allowed file -> visible
excluded file -> inaccessible
Byte personal memory -> inaccessible
unlisted project state -> inaccessible
```

### 32.4 Budget tests

If `max_tool_calls = 5`, an attempted sixth tool call must not execute.

Budget exhaustion must be observable and deterministically classified.

### 32.5 Reporting tests

A report with findings but no required evidence must not become `COMPLETED`.

A malformed report must fail validation.

### 32.6 Receipt tests

Changing one byte of a frozen artifact must change the corresponding SHA-256 hash.

Under the deterministic executor, identical frozen input must produce identical deterministic artifact hashes. Timestamp fields may differ.

### 32.7 Failure-injection tests

The test suite must deliberately exercise:

- executor crash;
- tool timeout;
- event-store failure;
- malformed report;
- budget exhaustion;
- cancellation;
- outcome-unknown classification.

## 33. Failure-aware engineering documentation

BSAP implementation must maintain a living `FAILURE_MAP.md`.

Each significant failure boundary must document:

- failure boundary;
- observable symptom;
- likely causes;
- first diagnostics;
- propagation path;
- safe recovery;
- data/state risk;
- explicit "do not" guidance where relevant;
- related tests.

A BSAP milestone is not complete until significant newly implemented failure surfaces are documented.

Example:

```text
Subsystem:
Byte Sub-Agent Protocol

Failure boundary:
Context packaging

Observable symptom:
Worker produces a conclusion based on missing prerequisite information.

Likely causes:
Context Manifest incomplete.
Parent summary incorrect.
Required artifact excluded.

First diagnostics:
Inspect frozen Context Manifest.
Compare report evidence against supplied sources.

Propagation:
Unsupported child conclusion may influence Byte's parent decision.

Safe recovery:
Reject report.
Correct the context package.
Create a new agent identity.

Do not:
Mutate the original running assignment.
Silently append missing context after execution.
```

## 34. Skill integration

BSAP's canonical definition remains this repository specification.

A future Byte Skill should operationalize BSAP by teaching Byte:

- when to evaluate delegation;
- how to construct a valid request;
- how to select context;
- how to respect the permission and budget contract;
- how to validate a report;
- how to record parent disposition.

The Skill is an operational layer, not the canonical protocol definition.

## 35. Memory integration

The protocol uses three distinct persistence roles.

### 35.1 Repository

The repository specification is the canonical source of truth for what BSAP is.

### 35.2 Byte working memory

Working memory stores only the compact operational invariants needed for Byte to remember that BSAP exists and how to behave when using it.

### 35.3 Semantic memory

Semantic memory stores architectural decisions, rationale, protocol-version milestones, and the location of the canonical specification.

Semantic memory must not become a competing full copy of the protocol specification.

## 36. Protocol invariants

BSAP v0.1 freezes the following invariants:

1. Every sub-agent has exactly one parent.
2. Every execution has a unique immutable agent ID.
3. A child receives explicit context, never implicit parent state.
4. Permissions are deny-by-default.
5. V0.1 children cannot create other children.
6. Running assignments cannot silently mutate.
7. Events are append-only and ordered.
8. Every completed worker produces a structured report.
9. Byte evaluates the report before using its conclusions.
10. Retry means a new execution identity.
11. Every execution reaches an explicit terminal outcome.
12. Executor implementation is hidden behind the BSAP interface.
13. A report may be `COMPLETED` without being accepted by Byte.
14. No external network or provider access is permitted in the deterministic v0.1 executor.
15. The deterministic harness validates protocol mechanics before a real model executor is introduced.

## 37. Acceptance criteria for BSAP v0.1 protocol harness

The protocol harness is accepted only when all of the following are true:

- one child can be requested, prepared, started, completed, and terminated;
- illegal lifecycle transitions are rejected;
- the prepared assignment is immutable;
- context access is restricted to the frozen manifest;
- write access is denied;
- network access is denied;
- recursive spawning is denied;
- configured budgets are enforced;
- events are ordered and append-only;
- required report fields are validated;
- an evidence-free report cannot become `COMPLETED`;
- Byte can record a parent disposition independently from child completion;
- request, context, policy, and report hashes are produced;
- a final receipt is generated;
- failure-injection cases are covered;
- `OUTCOME_UNKNOWN` is tested;
- relevant failure boundaries are documented in `FAILURE_MAP.md`;
- the full deterministic test suite passes.

## 38. Deliberately deferred capabilities

The following are future protocol changes and must not be smuggled into the v0.1 implementation:

- multiple concurrent children;
- writable child workspaces;
- isolated Git worktrees for child modification;
- recursive delegation;
- child-to-child communication;
- broad autonomous spawning;
- provider-native child-agent APIs;
- shared mutable memory;
- automatic semantic-memory writes;
- dynamic permission escalation;
- cross-project context;
- long-lived permanent child identities.

Each requires a deliberate design and protocol-version decision.

## 39. Next milestone after specification approval

After this specification is reviewed and accepted in repository form, implementation planning should define the smallest deterministic BSAP v0.1 vertical slice.

The implementation plan must preserve the protocol's failure-aware engineering requirements and must not add deferred capabilities.


# BSAP Failure Map

This is the living failure-aware engineering document for the Byte Sub-Agent Protocol.

A BSAP milestone is not complete until significant newly introduced failure surfaces are documented here and connected to tests.

## Context packaging

**Observable symptom:** A child produces a plausible conclusion without information required to justify it, or attempts to read an excluded file.

**Likely causes:** Incomplete Context Manifest, incorrect parent summary, excluded required artifact, stale project state, or an executor trying to bypass the frozen manifest.

**First diagnostics:** Inspect the frozen Context Manifest, compare report evidence with supplied sources, verify the manifest hash, and inspect `context.denied` / tool events.

**Propagation:** Unsupported child conclusions may influence Byte's parent decision.

**Safe recovery:** Reject the report, correct the context package, and create a new execution identity.

**Data/state risk:** EXEC-01 is read-only, so the primary risk is epistemic contamination rather than project mutation.

**Do not:** Mutate a running assignment or silently append missing context after execution.

**Related tests:** `tests/test_sandbox.py`, `tests/test_failure_injection.py::test_context_denial_is_known_failure_not_unknown_outcome`.

## Permission enforcement

**Observable symptom:** A child requests write, network, or recursive-spawn capability, or invokes a tool outside its effective permissions.

**Likely causes:** Invalid prepared policy, overly broad tool surface, missing deny-by-default enforcement, or tool-wrapper bypass.

**First diagnostics:** Inspect the frozen permissions and policy hash, then inspect ordered permission events.

**Propagation:** Unauthorized state or external effects could occur in later writable/networked protocol versions.

**Safe recovery:** Fail closed before `RUNNING` for forbidden v0.1 permissions; deny unauthorized tool calls before side effects.

**Data/state risk:** High in future write-capable versions; deliberately bounded in EXEC-01.

**Do not:** Treat a requested capability as granted authority.

**Related tests:** `tests/test_executor_and_manager.py::test_prepare_rejects_permissions_forbidden_by_v01`, `tests/test_sandbox.py::test_denied_capabilities_fail_closed`.

## Budget exhaustion

**Observable symptom:** A worker attempts more steps or tool calls than the frozen budget permits.

**Likely causes:** Overlong scripted execution, incorrect budget sizing, or runaway future model behavior.

**First diagnostics:** Inspect the prepared budget and `budget.exhausted` event.

**Propagation:** Without enforcement, a child could consume unbounded compute or tools.

**Safe recovery:** Block the excess action before it starts and classify the deterministic execution as `FAILED`.

**Do not:** Allow an over-budget action and account for it afterward.

**Related tests:** `tests/test_sandbox.py`, `tests/test_failure_injection.py::test_budget_exhaustion_blocks_execution_and_is_failed`.

## Executor interruption and tool timeout

**Observable symptom:** The executor crashes or a governed tool fails to return.

**Likely causes:** Executor defect, deterministic test timeout, runtime failure, or later provider/tool interruption.

**First diagnostics:** Identify the final confirmed event and determine whether the interrupted operation is known to be read-only and effect-free.

**Propagation:** The protocol may be unable to distinguish ordinary failure from uncertain effects.

**Safe recovery:** Classify known read-only timeout/crash cases as `FAILED`; use `OUTCOME_UNKNOWN` when effects cannot be proved.

**Do not:** Convert uncertainty into `FAILED` merely for convenience.

**Related tests:** `tests/test_failure_injection.py::test_executor_crash_before_tools_is_failed`, `tests/test_failure_injection.py::test_read_only_tool_timeout_is_failed`, `tests/test_failure_injection.py::test_unknown_effect_after_tool_started_is_outcome_unknown`.

## Event-store / audit loss

**Observable symptom:** Event recording fails after execution has begun.

**Likely causes:** Event-store failure, serialization error, storage outage, or runtime interruption.

**First diagnostics:** Inspect the final persisted sequence number and determine whether execution continued beyond the last durable event.

**Propagation:** BSAP can no longer prove a complete audit trail.

**Safe recovery:** Classify the execution as `OUTCOME_UNKNOWN` and do not accept its conclusions as a completed governed run.

**Do not:** Reconstruct missing events from memory and present them as original audit evidence.

**Related tests:** `tests/test_failure_injection.py::test_event_store_failure_after_start_is_outcome_unknown`.

## Report validation

**Observable symptom:** A child claims completion with missing fields, missing evidence, or findings that are not linked to evidence.

**Likely causes:** Completion-contract violation, malformed executor output, or future model schema failure.

**First diagnostics:** Validate the report against the frozen completion contract and inspect evidence-to-finding links.

**Propagation:** Unsupported conclusions may be presented as trustworthy.

**Safe recovery:** Refuse `COMPLETED`; classify the deterministic execution as `FAILED`.

**Do not:** Invent or repair missing evidence on behalf of the child.

**Related tests:** `tests/test_reporting.py`, `tests/test_failure_injection.py::test_malformed_report_cannot_complete`.

## Cancellation

**Observable symptom:** The parent cancels a prepared child or execution signals cancellation.

**Likely causes:** Parent decision, superseded assignment, or controlled executor cancellation.

**First diagnostics:** Inspect lifecycle state immediately before cancellation and verify the active-child slot is released.

**Propagation:** Incorrect cleanup could block future children or mislabel cancellation as failure.

**Safe recovery:** Record `CANCELLED`, terminate resources, preserve the terminal outcome, and release the active slot.

**Do not:** Reuse the cancelled agent identity for a retry.

**Related tests:** `tests/test_failure_injection.py::test_parent_can_cancel_prepared_child_and_release_slot`, `tests/test_failure_injection.py::test_cancellation_is_distinct_terminal_outcome`.

## Parent over-trust

**Observable symptom:** Byte uses a child's conclusion without an explicit parent disposition.

**Likely causes:** Child completion conflated with acceptance or delegation treated as authority transfer.

**First diagnostics:** Verify a separate `ParentDisposition` exists and inspect accepted/rejected finding IDs.

**Propagation:** Incorrect child conclusions become parent decisions.

**Safe recovery:** Return the report to parent review before further action.

**Do not:** Treat `COMPLETED` as `ACCEPTED`.

**Related tests:** `tests/test_executor_and_manager.py::test_parent_disposition_is_separate_from_child_completion`, `tests/test_end_to_end.py`.

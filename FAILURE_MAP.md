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

## EXEC-02 provider unavailable or transport failure

**Observable symptom:** A model turn emits `provider.failed`, the child terminates `FAILED`, or the Byte-MCP connection cannot be established.

**Likely causes:** Byte-MCP is stopped, the Streamable HTTP endpoint is unreachable, the MCP client dependency is unavailable, provider infrastructure rejects the request, or an unexpected transport exception occurs.

**First diagnostics:** Inspect the `provider.failed` category, confirm the local Byte-MCP endpoint is reachable, and run the schema probe before any live canary. Verify the receipt identifies the expected transport/model without inspecting secrets.

**Propagation:** The child cannot continue its investigation and must not fabricate a report from incomplete evidence.

**Safe recovery:** Preserve the failed execution receipt. Correct the runtime/transport problem and create a new BSAP execution identity for any retry.

**Data/state risk:** Low for project state because EXEC-02 is read-only; the main risk is incomplete or misleading investigation state.

**Do not:** Retry invisibly, reuse the failed agent identity, switch models automatically, or expose raw provider payloads/credentials in events.

**Related tests:** `tests/test_model_executor.py::test_provider_failure_emits_once_and_does_not_retry`, `tests/test_byte_mcp_transport.py::test_transport_does_not_retry_normalized_invoker_failure`, `tests/test_failure_injection.py::test_provider_failure_has_explicit_safe_classification`.

## EXEC-02 provider timeout

**Observable symptom:** Provider communication is classified as `timeout` and the child terminates `FAILED`.

**Likely causes:** Byte-MCP/provider latency, upstream overload, or a transport timeout.

**First diagnostics:** Inspect the safe failure category and confirm no second provider attempt occurred under the same child identity.

**Propagation:** The current child has no valid final report.

**Safe recovery:** Treat the attempt as failed; only a deliberate new BSAP execution may retry.

**Data/state risk:** Read-only child state only.

**Do not:** Hide the timeout behind automatic retry, fallback, or model substitution.

**Related tests:** `tests/test_model_transport.py::test_transport_error_exposes_safe_category_without_raw_provider_payload`, `tests/test_failure_injection.py::test_provider_failure_has_explicit_safe_classification`.

## EXEC-02 Byte-MCP `nvidia_query` contract drift

**Observable symptom:** The live schema probe fails with `contract_mismatch` before a provider call.

**Likely causes:** `nvidia_query` was removed, duplicated, renamed, or its `prompt`, `model`, or `system_prompt` input fields changed.

**First diagnostics:** Read the live `list_tools` schema from Byte-MCP and compare it with the EXEC-02 adapter contract.

**Propagation:** A stale adapter could otherwise send malformed requests or silently bind the wrong provider contract.

**Safe recovery:** Stop before provider execution and deliberately update the transport contract plus tests.

**Data/state risk:** None when the gate works because no provider call is made.

**Do not:** Guess argument names, bypass the probe, or infer the live overlay from the older public Byte-MCP source tree.

**Related tests:** `tests/test_byte_mcp_transport.py::test_expected_nvidia_query_schema_is_accepted`, `tests/test_byte_mcp_transport.py::test_schema_mismatch_fails_closed`.

## EXEC-02 malformed model JSON or envelope

**Observable symptom:** A turn emits `protocol.failed` with codes such as `invalid_json`, `unknown_type`, `invalid_envelope`, `unknown_tool`, `invalid_arguments`, or `invalid_report`.

**Likely causes:** The model returns prose around JSON, malformed JSON, an unsupported envelope, an unapproved tool, wrong argument types, or malformed report fields.

**First diagnostics:** Inspect only the safe protocol failure code and the prior observable tool/model events. Do not attempt to recover hidden reasoning.

**Propagation:** No model action may execute unless the strict parser accepts it.

**Safe recovery:** Terminate the current execution as `FAILED`. Adjust prompt/protocol design only if repeated evidence shows a contract problem; a provider retry requires a new child identity.

**Data/state risk:** Low because parsing happens before governed tool execution for that turn.

**Do not:** Extract JSON from prose, repair malformed output heuristically, or treat unknown tools as near matches.

**Related tests:** `tests/test_model_protocol.py::test_prose_wrapped_json_is_rejected`, `tests/test_model_protocol.py::test_invalid_tool_envelopes_are_rejected`, `tests/test_model_protocol.py::test_malformed_report_shapes_are_rejected`, `tests/test_model_executor.py::test_malformed_json_emits_protocol_failure_once_and_does_not_retry`, `tests/test_failure_injection.py::test_protocol_failure_has_explicit_safe_classification`.

## EXEC-02 provider success with invalid BSAP report

**Observable symptom:** The provider returns a syntactically valid final-report envelope, but `validate_report` rejects completion because required fields/evidence semantics are invalid.

**Likely causes:** Missing completion-contract fields, empty required evidence, unlinked findings, or non-completed report status.

**First diagnostics:** Validate the parsed `BsapReport` against the frozen completion contract and inspect finding/evidence linkage.

**Propagation:** Unsupported findings could otherwise be promoted to a successful child result.

**Safe recovery:** Classify the child as `FAILED`; do not repair evidence on the child's behalf.

**Data/state risk:** Epistemic rather than project mutation.

**Do not:** Convert structurally valid provider output into `COMPLETED` without semantic report validation.

**Related tests:** `tests/test_reporting.py`, `tests/test_failure_injection.py::test_malformed_report_cannot_complete`.

## EXEC-02 unauthorized tool or context escape

**Observable symptom:** `permission.denied` is emitted, or repository access raises `ContextAccessDenied`.

**Likely causes:** The child requests an ungranted known capability, an unknown tool, an unapproved test identifier, or a file outside the frozen Context Manifest.

**First diagnostics:** Compare the request with the immutable permission set, approved test registry, and frozen file list.

**Propagation:** Without fail-closed enforcement, a child could expand its own authority.

**Safe recovery:** Deny before side effects and terminate according to the existing manager failure classification.

**Data/state risk:** Potentially high if bypassed; deliberately bounded by EXEC-02's read-only controls.

**Do not:** Auto-expand context or permissions because the model requested them.

**Related tests:** `tests/test_model_executor.py::test_ungranted_test_request_is_denied_by_tool_dispatcher`, `tests/test_sandbox.py::test_read_is_limited_to_explicit_context`, `tests/test_sandbox.py::test_unknown_host_test_identifier_is_denied_before_tool_started`, `tests/test_failure_injection.py::test_context_denial_is_known_failure_not_unknown_outcome`.

## EXEC-02 model step or tool-call budget exhaustion

**Observable symptom:** `budget.exhausted` is emitted and execution stops before the excess model turn or tool action begins.

**Likely causes:** The investigation is too broad, the model loops, or the frozen budget is undersized.

**First diagnostics:** Inspect the prepared `Budget`, count `model.requested` and `tool.started` events, and locate the final `budget.exhausted` event.

**Propagation:** Without the gate, model/provider usage or tool execution could become unbounded.

**Safe recovery:** Terminate the execution and, if justified, create a new child with a deliberately revised budget.

**Data/state risk:** Resource-consumption risk; project mutation remains blocked.

**Do not:** Let the child increase its own budget or account for an over-budget action after execution.

**Related tests:** `tests/test_model_executor.py::test_step_budget_blocks_second_model_turn_before_transport_send`, `tests/test_sandbox.py::test_tool_budget_blocks_call_before_tool_started`, `tests/test_failure_injection.py::test_budget_exhaustion_blocks_execution_and_is_failed`.

## EXEC-02 unknown or misconfigured approved test

**Observable symptom:** `tests.run` is denied before `tool.started`, or an approved host command fails for environmental reasons.

**Likely causes:** The model requested an identifier absent from the frozen test registry, or the parent configured an invalid executable/working directory.

**First diagnostics:** Compare the requested stable identifier with the `AllowlistedTestRunner` registry. For an approved test, inspect only bounded stdout/stderr and exit code.

**Propagation:** An unknown identifier must never become arbitrary command execution.

**Safe recovery:** Deny unknown identifiers. Correct parent-owned test configuration and start a new execution when needed.

**Data/state risk:** Host execution risk is bounded by the parent-defined command tuple and `shell=False`.

**Do not:** Treat the test identifier as command text, concatenate it into a shell string, or accept model-supplied executable arguments.

**Related tests:** `tests/test_test_runner.py::test_unknown_identifier_is_denied_before_subprocess`, `tests/test_test_runner.py::test_subprocess_is_invoked_with_shell_false`, `tests/test_sandbox.py::test_unknown_host_test_identifier_is_denied_before_tool_started`.

## EXEC-02 approved test timeout

**Observable symptom:** `tool.failed` is emitted with `reason=timeout`; the manager records a known `FAILED` outcome.

**Likely causes:** The allowlisted test hangs or exceeds its parent-defined timeout.

**First diagnostics:** Inspect the approved test identifier and timeout configuration; do not expose arbitrary process details to the child.

**Propagation:** The child lacks that test evidence and cannot safely continue as though the test completed.

**Safe recovery:** Stop the current execution. Diagnose the approved test outside the child and create a new execution if appropriate.

**Data/state risk:** Limited to the preapproved read/test process boundary.

**Do not:** Remove the timeout or rerun invisibly under the same identity.

**Related tests:** `tests/test_test_runner.py::test_timeout_is_classified_without_returning_partial_process_state`, `tests/test_sandbox.py::test_timed_out_host_test_emits_tool_failed_and_raises_tool_timeout`, `tests/test_failure_injection.py::test_read_only_tool_timeout_is_failed`.

## EXEC-02 bounded test-output truncation

**Observable symptom:** Captured stdout/stderr ends with `...[truncated]`.

**Likely causes:** An approved test produced more output than its configured `max_output_chars`.

**First diagnostics:** Inspect the approved test specification and whether the evidence needed by the child appears before truncation.

**Propagation:** Important evidence may be absent from the returned result if logs are excessively verbose.

**Safe recovery:** Reduce test verbosity or deliberately increase the parent-owned bound in a new execution.

**Data/state risk:** No project mutation; context-quality risk only.

**Do not:** Remove output bounds merely to expose complete logs to the child.

**Related tests:** `tests/test_test_runner.py::test_output_is_bounded_with_visible_truncation_marker`.

## EXEC-02 nested async runtime misuse

**Observable symptom:** The synchronous Byte-MCP invoker fails with `transport_failure` before constructing async work when called inside an already-running event loop.

**Likely causes:** The synchronous adapter is invoked from an async host without an isolation boundary.

**First diagnostics:** Confirm whether `asyncio.get_running_loop()` succeeds in the calling thread.

**Propagation:** Naively nesting `asyncio.run()` can leak unawaited coroutine state or fail unpredictably.

**Safe recovery:** Invoke the synchronous adapter from a non-async boundary or add a deliberately designed async transport in a later milestone.

**Data/state risk:** No provider call should begin when the guard works.

**Do not:** Create the coroutine first and only then discover the nested event loop.

**Related tests:** `tests/test_byte_mcp_transport.py::test_synchronous_invoker_rejects_nested_event_loop`.

## EXEC-02 audit/event-store loss during model execution

**Observable symptom:** The event store fails after model/tool execution begins and BSAP cannot prove a complete ordered audit trail.

**Likely causes:** Event-store failure, serialization error, or runtime interruption.

**First diagnostics:** Identify the final durable event and whether any model/tool operation could have occurred afterward.

**Propagation:** The protocol can no longer prove the exact governed execution history.

**Safe recovery:** Preserve `OUTCOME_UNKNOWN`; do not promote a model report to completed governed output.

**Data/state risk:** EXEC-02 tools are read-only, but audit integrity is still a protocol invariant.

**Do not:** Reconstruct missing model/tool events from memory or provider output.

**Related tests:** `tests/test_failure_injection.py::test_event_store_failure_after_start_is_outcome_unknown`.

## EXEC-02 parent disposition validation

**Observable symptom:** Parent-disposition JSON is rejected because it references unknown finding IDs, overlaps accepted/rejected IDs, has an invalid result, or no completed child report exists.

**Likely causes:** Parent review input does not match the actual child report.

**First diagnostics:** Compare accepted/rejected IDs with the completed report's finding IDs and validate the disposition result against `ParentDispositionResult`.

**Propagation:** Invalid review metadata could otherwise misrepresent which child findings Byte actually accepted.

**Safe recovery:** Reject the disposition input without altering the child's terminal outcome; submit a corrected disposition.

**Data/state risk:** Decision-provenance risk only.

**Do not:** Auto-accept the known canary diagnosis or derive disposition from keywords.

**Related tests:** `tests/test_exec02_end_to_end.py::test_parent_disposition_rejects_unknown_finding_ids`, `tests/test_exec02_end_to_end.py::test_parent_disposition_requires_completed_report`, `tests/test_executor_and_manager.py::test_parent_disposition_is_separate_from_child_completion`.

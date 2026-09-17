# BSAP Failure Map

This is the living failure-aware engineering document for the Byte Sub-Agent Protocol.

A BSAP milestone is not complete until significant newly introduced failure surfaces are documented here and connected to tests.

## Context packaging

**Observable symptom:** A child produces a plausible conclusion without information required to justify it.

**Likely causes:** Incomplete Context Manifest, incorrect parent summary, excluded required artifact, stale project state.

**First diagnostics:** Inspect the frozen Context Manifest, compare report evidence with supplied sources, verify manifest hash, confirm excluded resources remained inaccessible.

**Propagation:** Unsupported child conclusions may influence Byte's parent decision.

**Safe recovery:** Reject or quarantine the report, correct the context package, create a new execution identity.

**Do not:** Mutate a running assignment or silently append missing context after execution.

## Permission enforcement

**Observable symptom:** A child attempts or appears able to perform an operation outside its granted capabilities.

**Likely causes:** Permission validation defect, overly broad executor tool surface, missing deny-by-default enforcement, tool wrapper bypass.

**First diagnostics:** Inspect frozen permissions, executor capability mapping, ordered events, and whether state actually changed.

**Propagation:** Unauthorized state may be modified.

**Safe recovery:** Stop execution, establish whether side effects occurred, classify FAILED or OUTCOME_UNKNOWN as appropriate, repair the boundary before retrying.

**Do not:** Assume a denied permission proves the underlying tool was inaccessible.

## Executor interruption

**Observable symptom:** The executor disappears, crashes, or loses communication during an active operation.

**Likely causes:** Runtime crash, tool timeout, communication failure, host failure.

**First diagnostics:** Identify the final confirmed event and determine whether an operation started without a confirmed completion.

**Propagation:** BSAP may be unable to determine the execution result.

**Safe recovery:** Use OUTCOME_UNKNOWN whenever effects cannot be proved.

**Do not:** Convert uncertainty into FAILED merely for convenience.

## Report validation

**Observable symptom:** A child claims completion but its report is malformed, incomplete, or lacks required evidence.

**Likely causes:** Missing required field, completion-contract violation, invalid evidence reference, executor reporting defect.

**First diagnostics:** Validate against the frozen completion contract, verify evidence references, inspect report hash and reporting events.

**Propagation:** Unsupported conclusions may be presented as trustworthy.

**Safe recovery:** Do not classify as COMPLETED until report validation succeeds.

**Do not:** Invent or repair missing evidence on behalf of the child.

## Parent over-trust

**Observable symptom:** Byte uses a child's conclusion without independently evaluating the report.

**Likely causes:** Missing parent disposition, delegation treated as authority transfer, child completion conflated with acceptance.

**First diagnostics:** Locate parent disposition and verify accepted/rejected findings and supporting evidence.

**Propagation:** Incorrect child conclusions become parent decisions.

**Safe recovery:** Return the report to parent review before further action.

**Do not:** Treat COMPLETED as ACCEPTED.

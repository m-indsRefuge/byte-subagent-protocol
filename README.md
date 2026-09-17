# Byte Sub-Agent Protocol

**BSAP** is a governed delegation protocol for Byte.

Its purpose is to allow Byte to delegate bounded engineering cognition to isolated child workers while Byte remains the parent orchestrator and retains responsibility for the final engineering decision.

## Current status

Protocol: **BSAP v0.1**

Status: **Approved design / deterministic protocol harness not yet implemented**

The canonical protocol definition is `BSAP_SPEC.md`.

## V0.1 constraints

- one active child at a time;
- delegation depth of one;
- read-only child;
- deny-by-default permissions;
- explicit frozen context;
- bounded execution;
- no recursive spawning;
- no external network access for the deterministic executor;
- append-only observable events;
- structured evidence-backed reports;
- explicit parent disposition;
- immutable execution receipts.

The first executor will be deterministic so protocol behavior can be validated independently from LLM behavior.

The next major milestone will introduce a genuine independent model session using the same protocol contract.

## Source of truth

This local Git repository is the canonical source of truth for BSAP.

Byte working memory should contain only compact operational rules. Semantic memory may retain architectural rationale and protocol history. A future Byte Skill may operationalize BSAP but does not replace this repository as the canonical definition.

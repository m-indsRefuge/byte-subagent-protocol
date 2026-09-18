# Byte Sub-Agent Protocol

**BSAP** is a governed delegation protocol for Byte.

Its purpose is to allow Byte to delegate bounded engineering cognition to isolated child workers while Byte remains the parent orchestrator and retains responsibility for the final engineering decision.

## Current status

Protocol: **BSAP v0.1**

Status: **BSAP-EXEC-01 deterministic protocol harness implemented and verified in the development sandbox.**

The canonical protocol definition is `BSAP_SPEC.md`.

## What EXEC-01 proves

The deterministic harness provides:

- one active child at a time;
- delegation depth of one;
- immutable prepared assignments;
- explicit frozen context;
- deny-by-default permissions;
- hard v0.1 denial of write, external network, and recursive spawn permissions;
- deterministic step and tool-call budgets;
- append-only ordered events;
- evidence-backed report validation;
- separate parent disposition;
- explicit `COMPLETED`, `FAILED`, `CANCELLED`, and `OUTCOME_UNKNOWN` outcomes;
- immutable execution receipts with SHA-256 bindings;
- failure injection for crashes, timeouts, budget exhaustion, malformed reports, cancellation, context denial, audit loss, and unknown outcomes.

EXEC-01 does **not** contain a real LLM child. The executor is intentionally deterministic so the protocol boundary can be validated independently from model behavior.

## Run the harness

```powershell
python -m pytest -v
$env:PYTHONPATH = "src"
python -W error -m bsap.demo
```

The deterministic demo investigates a controlled milliseconds-to-seconds configuration defect without modifying files or calling any external provider.

## Next milestone

The next separate milestone is **BSAP-EXEC-02**: a genuine independent, read-only model worker implementing the same `Executor` interface and governance contract.

## Source of truth

This Git repository is the canonical source of truth for BSAP.

Byte working memory should contain only compact operational rules. Semantic memory may retain architectural rationale and protocol history. The Byte Skill operationalizes BSAP but does not replace this repository as the canonical definition.

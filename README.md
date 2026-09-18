# Byte Sub-Agent Protocol

**BSAP** is a governed delegation protocol for Byte.

Its purpose is to allow Byte to delegate bounded engineering cognition to isolated child workers while Byte remains the parent orchestrator and retains responsibility for the final engineering decision.

## Current status

Protocol: **BSAP v0.1**

Status: **BSAP-EXEC-02 deterministic implementation complete on the feature branch; live Nemotron Lightning acceptance is pending.**

The canonical protocol definition is `BSAP_SPEC.md`. The approved EXEC-02 design is `docs/superpowers/specs/2026-09-18-bsap-exec-02-real-read-only-model-worker-design.md`.

## EXEC-01 reference harness

The deterministic EXEC-01 harness remains available and continues to prove:

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
- immutable execution receipts with SHA-256 bindings.

Run the reference harness with:

```powershell
python -m pytest -q
$env:PYTHONPATH = "src"
python -W error -m bsap.demo
```

## EXEC-02 model worker

EXEC-02 adds a provider-neutral `ModelTransport`, strict JSON model protocol, bounded `ModelExecutor`, real allowlisted host-side tests, explicit provider/protocol failure classification, and a Byte-MCP NVIDIA transport targeting the governed `lightning` alias.

The child itself remains read-only and has no arbitrary shell, provider, or network authority. It may only request the governed tools approved in its frozen assignment:

- `repository.read`;
- `repository.search`;
- `tests.run` for stable parent-approved test identifiers.

`tests.run` executes predefined host commands with `shell=False`, an explicit working directory, timeout, and bounded output. Model-supplied command text is never accepted.

The model interaction is iterative but bounded: each model turn consumes step budget, each governed tool operation consumes tool-call budget, and no hidden provider retry or model substitution is performed.

## Installation

Core deterministic BSAP has no runtime dependencies beyond Python 3.12+.

Development tools:

```powershell
python -m pip install -e ".[dev]"
```

The live Byte-MCP/NVIDIA adapter is optional:

```powershell
python -m pip install -e ".[dev,nvidia]"
```

NVIDIA credentials remain owned by the existing Byte-MCP runtime and are not stored by BSAP.

## Deterministic verification

Before any live model call:

```powershell
python -m ruff check .
python -m pytest -q -W error
$env:PYTHONPATH = "src"
python -W error -m bsap.demo
python -m compileall -q src tests
git diff --check
```

## Live Lightning canary

The live canary deliberately contains a tiny milliseconds-to-seconds defect and gives the child a frozen two-file context plus one allowlisted test. The child must independently choose governed tools and produce an evidence-backed `BsapReport`.

With the local Byte-MCP runtime available at its default URL:

```powershell
$env:PYTHONPATH = "src"
python -W error -m bsap.live_canary
```

The CLI first probes the live `nvidia_query` schema. Schema mismatch is a hard stop before a provider call. A completed child report prints `PARENT_DISPOSITION_REQUIRED`; Byte must then independently evaluate the observable report/receipt and provide exactly one disposition JSON line. Child completion and parent acceptance remain separate.

Live acceptance evidence is recorded in `docs/EXEC02-LIVE-CANARY.md`. Until that document records an actual completed run, EXEC-02 is not considered fully accepted.

## Source of truth

This Git repository is the canonical source of truth for BSAP.

Byte working memory should contain only compact operational rules. Semantic memory may retain architectural rationale and protocol history. The Byte Skill operationalizes BSAP but does not replace this repository as the canonical definition.

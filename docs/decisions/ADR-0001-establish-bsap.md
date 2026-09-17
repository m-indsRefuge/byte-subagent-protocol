# ADR-0001: Establish the Byte Sub-Agent Protocol

**Date:** 2026-09-17  
**Status:** Accepted

## Context

Byte needs a governed method for delegating bounded engineering work to an isolated child worker without transferring responsibility for the parent task.

## Decision

Establish the Byte Sub-Agent Protocol (BSAP).

BSAP v0.1 begins with one parent, one active child, delegation depth one, read-only execution, explicit context manifests, deny-by-default permissions, bounded execution, append-only events, evidence-backed reports, explicit parent disposition, immutable receipts, and a deterministic executor first.

The executor is abstracted behind the protocol so a genuine independent model session can later replace the deterministic executor without changing Byte's parent-facing contract.

## Consequences

BSAP becomes a capability of Byte rather than a feature owned by any single experiment or application.

The Recursive Agent Laboratory may act as a consumer and testbed, but does not own the protocol.

The local Git repository is the canonical source of truth.

Byte working memory should retain compact behavioral invariants; semantic memory records design rationale and evolution; a future Byte Skill may operationalize BSAP.

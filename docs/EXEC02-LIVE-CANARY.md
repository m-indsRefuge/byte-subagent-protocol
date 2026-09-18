# BSAP-EXEC-02 Live Lightning Canary

## Status

**Pending live acceptance.**

The deterministic EXEC-02 implementation and canary harness are present on `feat/bsap-exec-02`. This document must not be marked complete until an actual Nemotron 3.5 Lightning run is performed through the live Byte-MCP `nvidia_query` tool and Byte records a separate parent disposition.

## Preconditions

- Full deterministic pytest suite passes with warnings treated as errors.
- Ruff passes on the operator's Python 3.12 checkout.
- `python -m compileall -q src tests` passes.
- `git diff --check` passes.
- EXEC-01 demo still passes under `-W error`.
- Byte-MCP live schema probe confirms exactly one `nvidia_query` tool whose input schema exposes `prompt`, `model`, and `system_prompt`.
- The governed model alias is `lightning`.
- Retries, fallback, and model substitution remain disabled.

## Live command

```powershell
$env:PYTHONPATH = "src"
python -W error -m bsap.live_canary
```

A completed child prints `PARENT_DISPOSITION_REQUIRED` and waits for exactly one JSON line from Byte containing `result`, `accepted_findings`, `rejected_findings`, and `rationale`.

## Acceptance evidence

The following fields are intentionally blank until a real run occurs:

- Run timestamp: **PENDING**
- Agent ID: **PENDING**
- Model alias: `lightning`
- Transport: `byte-mcp-nvidia`
- Terminal outcome: **PENDING**
- Ordered governed tool requests: **PENDING**
- Finding IDs: **PENDING**
- Request SHA-256: **PENDING**
- Context-manifest SHA-256: **PENDING**
- Policy SHA-256: **PENDING**
- Report SHA-256: **PENDING**
- Parent disposition: **PENDING**
- Hidden retries: `0` required
- Fallbacks: `0` required
- Model substitutions: `0` required

If the live canary fails, record the real provider/protocol failure classification rather than replacing these fields with expected values.

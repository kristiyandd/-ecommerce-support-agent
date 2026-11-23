# ADR-6: Ruff hardening without suppressions

Status: accepted (2026-11-23)

## Context
The code-quality standard asks for typed errors, small signatures and no magic values.

## Decision
Added BLE, TRY, ARG, DTZ, PLR0912, PLR0913 and PLR2004 (PLR2004 is off in tests). The root causes are fixed with named exception classes, parameter objects (`TurnPipeline`, `ServiceSettings`) and `_config` for the uniform rule signature. The three broad `except` blocks log with `logger.exception`: the provider boundary (`orchestrator.py`) and the turn boundary (`service.py`) also audit the error; the post-outcome audit writer (`service._record_after_the_fact`) only logs, because a failing audit must not change what the customer is told.

## Alternatives considered
Blanket per-file ignores, which hide new problems.

## Consequences
There are no inline suppressions in `src/`.

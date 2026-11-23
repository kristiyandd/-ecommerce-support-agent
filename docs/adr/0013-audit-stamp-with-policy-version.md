# ADR-13: Every audit record carries prompt, policy and model versions

Status: accepted (2026-11-23)

## Context
A decision must be traceable to the rules, prompt and model in force when it was made.

## Decision
A frozen `AuditStamp(prompt_version, policy_version, model_id)` is built at the composition root from `SYSTEM_PROMPT_VERSION`, the `version` in `config/policy.json` and `ModelClient.model_id`. The single `Auditor` writes it onto every `AuditEntry`.

## Alternatives considered
Logging versions once at start-up (lost when logs rotate, or when the config is reloaded mid-run).

## Consequences
Every decision is self-describing. A version bump in `policy.json` is visible per decision.

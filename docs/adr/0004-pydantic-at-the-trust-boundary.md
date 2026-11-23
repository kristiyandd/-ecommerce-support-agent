# ADR-4: pydantic at the trust boundary only

Status: accepted (2026-11-23)

## Context
Tool arguments come from the model, which is untrusted output. The policy file is external input. Hand-written validation and JSON Schema generation are error-prone.

## Decision
`pydantic==2.14.4` covers tool argument models (`extra=forbid`, strict, frozen), validation of tool calls, JSON Schema for the tool definitions, and loading the policy file in the adapter. Domain and policy stay on frozen dataclasses, and import-linter enforces that. The pydantic mypy plugin is enabled in `pyproject.toml`.

## Alternatives considered
Stdlib-only validation (the first version). It worked, but duplicated what pydantic does reliably.

## Consequences
One pinned and audited runtime dependency. The schemas sent to the model come from the same models that validate the calls.

# ADR-7: Dependency audit with pip-audit

Status: accepted (2026-11-23)

## Context
Even one runtime dependency plus dev tools can carry known vulnerabilities.

## Decision
`pip-audit --skip-editable` runs in `scripts.check` and fails on any known advisory. Any future ignore needs an ADR entry with a rationale and a review date.

## Alternatives considered
Dependabot only (not available locally or before the repository is pushed).

## Consequences
The check needs network access, about 3 s. Offline, it fails and has to be run again.

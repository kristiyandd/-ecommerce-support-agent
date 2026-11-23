# ADR-5: Layer contracts enforced by import-linter

Status: accepted (2026-11-23)

## Context
Three builders wrote code in parallel, and layering written only in docs drifts.

## Decision
Layers, outermost first: cli, evaluation or harness, harness_checks, composition, adapters, application, policy, domain. `domain` and `policy` may not import pydantic or `mock_env`. `application` may not import `mock_env`. `lint-imports` runs inside `scripts.check`.

## Alternatives considered
Code review only. It missed the policy-to-pydantic import until the contract existed.

## Consequences
A boundary violation fails the build. The pydantic policy model moved to `adapters/policy_file.py`.

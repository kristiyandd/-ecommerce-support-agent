# ADR-1: Plain Python package and CLI

Status: accepted (2026-11-23)

## Context
The reviewer must run the example requests locally. The assignment expects no UI, deployment or infrastructure.

## Decision
A Python 3.13 package with `python -m support_agent ask` and `run-scenarios`. No web framework.

## Alternatives considered
A FastAPI service (more setup, no review value). A notebook (not testable or repeatable).

## Consequences
One `pip install`, no services to start. An HTTP adapter can be added later behind the `SupportService` facade.

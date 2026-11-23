# ADR-3: Policy as code in a versioned config file

Status: accepted (2026-11-23)

## Context
Thresholds and limits are business choices. The 50.00 and 100.00 EUR defaults are placeholders.

## Decision
`config/policy.json` (version `policy/v1`, currency, thresholds, refundable statuses) is loaded at the composition root into a frozen `PolicyConfig`. The rules are small pure functions run in a fixed order.

## Alternatives considered
Constants in code (a change needs a deploy and leaves no trail). A rules engine (overkill for 8 rules).

## Consequences
Changing a limit is a reviewed, versioned data change. Policy is unit-tested without I/O.

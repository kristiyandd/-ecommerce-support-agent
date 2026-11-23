# ADR-10: Customer-scoped repositories: not yours equals not found

Status: accepted (2026-11-23)

## Context
The model chooses order IDs, and an ownership check that the model can talk its way around leaks data.

## Decision
`ContextBuilder` builds repositories from the authenticated customer_id only. `find_order` returns None for a foreign order and for a missing one alike, and never checks who owns it.

## Alternatives considered
An ownership check inside each tool (easy to forget in a new tool). Distinct errors (enables enumeration).

## Consequences
No tool can read another customer's data. Probing is not alerted on yet (see Left incomplete).

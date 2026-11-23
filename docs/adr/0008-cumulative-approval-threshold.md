# ADR-8: Cumulative approval threshold per order

Status: accepted (2026-11-23)

## Context
A per-request threshold let a customer split one large refund into smaller requests that never reached a human.

## Decision
Rule 7 compares the order's issued refunds plus the current request with `approval_threshold`. The customer cap was already cumulative. Policy reads only `order_refunds` from `RefundCheck`, so there is no new port and policy stays pure.

## Alternatives considered
Keep it per request and document the risk. The owner chose against this.

## Consequences
Two proposals made in parallel that together cross the threshold end as CONFIRMATION_STALE, and asking again escalates. Replays are unaffected.

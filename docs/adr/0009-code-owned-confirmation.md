# ADR-9: Confirmation is owned by code, not the model

Status: accepted (2026-11-23)

## Context
An irreversible action needs real customer consent. A model must not be able to confirm for the customer.

## Decision
`request_refund` only stores a `ProposedRefund` with an idempotency key (sha256 of customer, order, item, quantity and the quantity already refunded). Only the customer's next message matching the affirmation list executes it. The confirmation is single use, bound to conversation, customer and exact parameters, and re-checked under a lock.

## Alternatives considered
A `confirm_refund` tool called by the model (the model could confirm by itself). One-step refunds (no consent).

## Consequences
Double confirmations, replays across conversations and stale proposals cannot pay twice or pay a changed amount. The affirmation list stands in for a UI confirm button.

# ADR-11: Code writes every money and outcome sentence

Status: accepted (2026-11-23)

## Context
A model can hallucinate amounts or announce refunds that never happened.

## Decision
`application/replies.py` holds every reason, money and outcome sentence, keyed by `ReasonCode`. The output check blocks model text that contains any amount, a foreign order ID (in common spellings: any case, a hyphen variant or a space), an email, an ISO date, or refund-outcome wording unless the records show a refund. A blocked text is replaced by a safe fallback.

## Alternatives considered
Allowing amounts that appear in tool results. The review showed contradictory amounts could get through.

## Consequences
A real model's prose cannot misstate money. The fallback occasionally makes a legitimate reply less helpful.

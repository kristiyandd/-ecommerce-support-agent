# ADR-2: Bounded agent loop with tool calls

Status: accepted (2026-11-23)

## Context
The mock boundary must be representative of a real LLM integration, and money must never depend on model judgement.

## Decision
The model drives a loop of at most 4 steps with tool calls (`list_my_orders`, `get_order`, `request_refund`, `escalate_to_human`). Safety lives outside the loop: refunds only propose, policy computes amounts, code confirms, and code writes every money sentence.

## Alternatives considered
One classify-and-extract call, then fixed code paths. Equally safe, but less faithful to a real agent, and each intent needs its own pipeline.

## Consequences
The same protocol works for a real provider. Malformed calls, unknown tools, loops and provider errors are testable with a scripted model.

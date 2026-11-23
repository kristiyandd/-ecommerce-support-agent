# ADR-12: Heuristic mock model behind the ModelClient port

Status: accepted (2026-11-23)

## Context
No paid API is needed, but the boundary must look like a real model integration.

## Decision
`HeuristicModel` implements `ModelClient` and speaks the same message and tool-call protocol. It reads only the latest user message and this turn's tool results, never reads the store, and uses generic keyword and pattern extraction. When unsure, it asks a clarifying question. `MODEL_PROVIDER` selects it (default `mock`).

## Alternatives considered
A recorded-response fake (it would encode the scenarios). A real provider (cost, non-determinism, no extra credit).

## Consequences
Its phrasing coverage is narrow (English keywords). Safety is proven with a scripted compromised model, not with the mock.

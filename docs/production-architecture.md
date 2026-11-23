# Production architecture (next steps)

How this capability would run against a real model and real traffic. The core does not change:
`SupportService` -> bounded `AgentLoop` -> `PolicyEngine` -> code-owned confirmation -> output check -> audit.
Everything below plugs in behind the existing ports (`ModelClient`, `CustomerDataFactory`, `AuditLog`).
Security risks and their controls are mapped in [threat-model.md](threat-model.md).

## Model routing and fallbacks
- A `RoutingModelClient` implements `ModelClient` and selects a provider model per turn. The default is a capable
  model for the tool loop. A cheaper model could take pure status questions only after evals show equal accuracy.
- Fallback order: primary model -> secondary model on a provider error or timeout -> the existing safe path
  (`MODEL_UNAVAILABLE` escalation). A fallback never skips policy: every model goes through the same tools, the
  same confirmation and the same output check, so a weaker fallback can only be less helpful, never less safe.
- The real `model_id` is already stamped on every audit record, so a decision can be traced to the model that
  produced it.

## Prompt versioning
- `SYSTEM_PROMPT_VERSION` (`support-agent/v1`) and the policy version (`policy/v1`) are on every audit record
  today. In production, prompts live as versioned files with a changelog. A prompt change is a release like
  code: it goes through the eval gate below.
- The prompt guides tone and tool choice only. Every safety property is enforced in code, so a prompt
  regression costs helpfulness, not money.

## Eval-gated releases
- `run-scenarios` is the gate: the example scenarios and the adversarial set. The altered seed, the fault tests and
  the compromised-model tests run in the test suite (`python -m scripts.check`). Safety comes first
  (a wrong-action rate of 0 and a data-leak count of 0 are hard gates), then correctness (escalation precision
  and recall), then helpfulness (the clarification rate).
- Any change to the prompt, model, policy file or code runs the gate in CI against the real model before
  release. `docs/eval-report.md` is the artifact attached to the release.

## Non-determinism
- A real model is not deterministic. Each eval case runs N times (start with N = 5 at temperature 0 and with
  the production setting). The report adds a consistency rate: the share of runs that agree on the decision
  class, the tools called and the escalation flag.
- The safety gate must hold on every run, not on average. Helpfulness metrics are reported with their spread.
  The scripted fault model stays deterministic for the safety tests.

## Cost and latency per turn
- Measured here (300 runs of the scenario-02 refund turn on the development laptop, mock model): orchestration
  overhead is about 3 ms median, under 5 ms p95, for 3 model calls and 2 tool calls. The model call dominates in production.
- Cost per turn = sum over model calls of (input tokens x input price + output tokens x output price). Input is
  the system prompt (about 640 characters), the four tool schemas, the conversation history and this turn's
  tool results. A refund turn makes 3 calls, so the history is re-sent 3 times. Prompt caching of the system
  prompt and the tool schemas is the first cost lever. Latency is about 3 x the model latency. Streaming the
  final reply helps perceived latency but not confirmation safety (code lines are appended after the check).
- Budget alarms: a cost and step count per trace, read from the audit log.

## Rate limits
- Per customer: a request rate and a refund-proposal rate (it limits probing and abuse). Per provider: a
  token-bucket client inside the `ModelClient` adapter, with backoff, so the domain never sees retries.
- Not needed yet: a single-process CLI has no concurrent traffic. The customer cap in `config/policy.json`
  already bounds money exposure.

## Async I/O behind the ports
- In production the model and database calls are network I/O. The ports become async (`async def complete`,
  async repositories) and the loop awaits them. The domain and policy stay synchronous and pure.
- Not needed yet: everything is in memory and the mock answers in microseconds. Async would add complexity
  with no benefit until there is real I/O.

## Batching (only off the request path)
- A customer turn is interactive and never batched. Batching fits offline work only: nightly eval runs over
  the adversarial set, re-scoring audit logs after a prompt change, and summarising escalations for the
  review queue.
- Not needed yet: there is no offline workload.

## Chunking (only for long conversation history)
- Tool results are small and scoped, so they are never chunked. The only growing input is conversation
  history. Past a token budget, older turns are summarised by code (decisions, order IDs, pending state)
  rather than sent verbatim, and pending confirmations are never summarised away.
- Not needed yet: conversations are a few turns.

## Persistence, idempotency and observability
- Refund records go to a database with a unique constraint on `idempotency_key`, which replaces the
  in-process lock. Pending confirmations and history go to a store with a TTL. The audit log goes to
  append-only storage.
- Metrics per trace: decision class, escalation reason, output-check blocks and model fallbacks. Alerts on a
  rise in OUTPUT_BLOCKED, on repeated not-found lookups (probing) and on refund volume per customer.

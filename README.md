# Ecommerce support agent

An AI-assisted customer-support capability for a small store. A customer sends a message with an
already-authenticated customer ID. The agent looks up that customer's orders and answers questions. It can
propose refunds, executing one only after the customer confirms, and hands cases to a human when the records
don't support the request. The model is mocked behind the same interface a real LLM would use.

## How to run

Requires Python 3.13. The runtime has one dependency, pydantic; the dev tools are pinned in
`requirements-dev.txt`.

PowerShell (Windows):
```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1          # if scripts are blocked: Set-ExecutionPolicy -Scope Process Bypass
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```
bash (Linux or macOS; in Git Bash on Windows use `py -3.13 -m venv .venv` and `source .venv/Scripts/activate`):
```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```
Then, with the venv active (the same commands in PowerShell and bash):
```
python -m support_agent run-scenarios
python -m support_agent run-scenarios --json
python -m support_agent ask --customer CUST-001 --message "Where is order ORD-100?"
python -m support_agent ask --customer CUST-001 --message "One of the wine glasses in order ORD-200 arrived broken. Can I get a refund for it?" --message "yes"
python -m support_agent ask --customer CUST-001 --message-file data/example-messages.txt
python -m pytest
python -m scripts.check
```
- `run-scenarios` runs the 4 example requests and the adversarial set, and exits 1 on any failure.
  `--json` prints the same as one JSON document. `--report docs/eval-report.md` regenerates the committed
  evaluation report (it overwrites that file).
- In `ask`, each extra `--message` is the next turn of the same conversation, so `--message "yes"` confirms a
  proposed refund. `--message-file` reads one message per line (UTF-8, with or without a BOM).
- Each `ask` process starts from the seed data; refunds live in memory only.
- Exit codes: 0 success; 1 a failing scenario or safety gate (`run-scenarios`); 2 a usage or configuration error
  (no message, unknown `MODEL_PROVIDER`, invalid `config/policy.json`).
- `python -m scripts.package` regenerates `claude-transcripts/INDEX.md` and builds the submission zip in a `dist/`
  folder next to the project folder.
- `MODEL_PROVIDER` selects the model and defaults to `mock`; no other provider is implemented. Only real
  environment variables are read: `.env.example` documents them, but no `.env` file is loaded.
- `python -m scripts.check` runs 8 steps:
  - ruff lint and ruff format;
  - the layer contracts (import-linter);
  - mypy --strict;
  - pytest;
  - an 85% coverage gate on domain, policy and application;
  - a secret scan (detect-secrets);
  - a dependency audit (pip-audit; needs network, and audits pip itself, hence the pip upgrade above).
- The pre-commit hooks in `.pre-commit-config.yaml` assume the venv is activated.

## What I implemented

```
CLI (ask, run-scenarios) ──> composition root ──> SupportService (one request in, one TurnResult out)
  SupportService ──> AgentLoop (≤4 model steps) ──> ModelClient port  [heuristic mock | scripted fake]
                 ──> ToolRegistry (pydantic-validated calls) ──> PolicyEngine (pure rules, config/policy.json)
                 ──> code-owned confirmation + idempotent RefundExecutor ──> customer-scoped repositories (mock_env)
                 ──> output check + code-written money lines ──> append-only audit (trace, prompt, policy, model)
```
The design choice is that safety lives outside the model:
- **Tools:** the model drives a bounded tool loop, as it would with a real LLM, but no tool can move money. `request_refund` only proposes.
- **Amounts:** policy computes every amount from the records with Decimal. Amounts the customer claims are compared with the records, never paid.
- **Confirmation:** a refund executes only when the customer's own next message confirms it. The confirmation is single use, bound to the exact parameters, re-checked against fresh data and idempotent.
- **Scoping:** repositories are scoped to the authenticated customer, so "not yours" looks exactly like "not found".
- **Replies:** code writes every sentence that states money or an outcome, and an output check blocks model text with amounts, foreign IDs or invented outcomes.
- **Policy as code:** thresholds and limits are a versioned data file (`config/policy.json`), not constants.

The layers are enforced by import-linter. The details are in [docs/design.md](docs/design.md), the decisions in [docs/adr/](docs/adr/README.md), and the risks in [docs/threat-model.md](docs/threat-model.md).

**What the four examples do:**
- **scenario-01:** status, carrier and tracking; no delivery estimate is invented.
- **scenario-02:** one wine glass (14.90 EUR) is offered and refunded after "yes".
- **scenario-03:** another customer's order: "I can't find order ORD-204 on your account".
- **scenario-04:** 29.90 EUR is offered (the record amount, not the 34.90 claimed), and an `amount_dispute` escalation records both amounts for a human to review the difference.

Results are in [docs/eval-report.md](docs/eval-report.md).

## Assumptions

- **Placeholder limits:** the human-approval threshold of **50.00 EUR** and the automatic-refund cap of **100.00 EUR** per customer are **placeholders** for the business to set (`config/policy.json`).
  - The threshold is cumulative per order, so a split refund can't avoid it.
  - The cap counts all of a customer's issued refunds, with no time window, because the records carry no dates.
- **Refundable orders:** `delivered` and `returned`. An `in_transit` order is not refundable; cancellation is out of scope.
- **Damage claims:** a damage claim without evidence gets a refund for the quantity the customer names, after confirmation. With no number, a one-unit line is refunded once; otherwise the agent asks how many. There is no photo or return flow to ask for.
- **Disputed claims:** a claimed amount above the records gets the record amount offered, and the difference is escalated. Quoting the order total is not a claim. Other currencies are never read as euros.
- **Confirmation:** a reply of "yes", "confirm" or similar in the next turn. It stands in for a UI confirm button.
- **The mock model:**
  - It is a deterministic stand-in that speaks the real message and tool-call protocol and never reads the store.
  - It understands keyword intents in English (human > refund > status > list orders), the store's order-ID pattern, and quantity, reason and item-name patterns. A status question without an order ID lists the customer's orders. When unsure, it asks a clarifying question.
  - It reads only the latest message and this turn's tool results. It is not NLU, and paraphrases a real model would handle make it ask instead.
  - Safety is proven with a scripted "compromised" model, not with the mock.
- **Seed data:** the mock environment's seed files are treated as immutable. Refund records are stored in its in-memory runtime store, and each run starts from the seed.

## What I deliberately left incomplete

| Missing | Risk | How it would be done |
|---|---|---|
| Real model adapter | The mock's language coverage is narrow | A `ModelClient` for Claude tool use, gated by the same evals run N times (see "Next") |
| Human-review workflow | Escalations are recorded but nobody picks them up | A queue plus review commands; `PENDING_REVIEW` → `ISSUED`/`REJECTED` already exists in the domain |
| Persistence | Everything is lost on restart, and the lock is in-process only | A database with a unique constraint on the idempotency key; TTL storage for pending confirmations |
| Interactive chat | Several turns need repeated `--message` flags | A REPL over the same `SupportService` |
| Behaviour checks on follow-up turns in the harness | After a "yes", only the final refund state is asserted | Allow `follow_up` behaviour specs in `expectations.json` |
| Alerting on order-ID probing | Enumeration attempts go unnoticed | Count not-found lookups per customer from the audit log |
| Return-status rule | A returned line is refunded even if the return was not received | A policy rule on `return_status` |
| Time-windowed limits, multi-currency | The cap never resets; only EUR is supported | Dates in the data; per-currency Money with FX rules |
| Property-based tests, metrics | Edge cases outside the examples may be missed; no runtime visibility | Hypothesis on Money and policy; per-trace metrics from the audit log |

## What I would do next

- **Real model:**
  - Add a Claude adapter behind `ModelClient` with prompt caching.
  - Run `run-scenarios` and the adversarial set N times per change (start with N = 5) and report consistency next to the hard safety gate (0 wrong actions, 0 leaks).
  - Add a larger adversarial set written by people who did not build it.
- **Persistence and scale:** a database for refunds and the audit log, async ports, per-customer rate limits, and model routing with fallbacks that never bypass policy.
- **Observability:** per-trace cost, latency and decision metrics, and alerts on output-check blocks, probing and refund volume.

The full plan is in [docs/production-architecture.md](docs/production-architecture.md).

Working documents: [brief](docs/brief.md), [decisions](docs/decisions.md), [analysis](docs/analysis.md),
[design](docs/design.md), [ADRs](docs/adr/README.md), [threat model](docs/threat-model.md),
[production architecture](docs/production-architecture.md), [evaluation report](docs/eval-report.md).

## Claude Code transcripts

`claude-transcripts/` holds the session files for this project directory, copied from
`%USERPROFILE%\.claude\projects\D--WorkEnv-ecommerce-support-agent\`. There is one session,
`208de43b-f1de-439e-8f9c-4711be235a1c`, with its 14 subagent transcripts and the tool outputs it saved
(listed in `claude-transcripts/INDEX.md`). `scripts/package.py` regenerates the index from the files present.

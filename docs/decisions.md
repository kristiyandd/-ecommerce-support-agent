# Decisions (P3 Foundation)

## 1. Stack

A plain Python package with a command-line interface: no web framework and no UI. The assignment
asks for no UI or deployment. The reviewer has to run the example requests easily, and a CLI over
a package with one runtime dependency (pydantic) does that with one `pip install` and no services.

## 2. Versions

- Interpreter: Python 3.13 (3.13.5, the newest from `py -0`; no other interpreter installed).
- Runtime dependencies: one, `pydantic==2.14.4` (pinned in `requirements.txt` and `pyproject.toml`).
  It is used only at the trust boundary (see ADR-4). Everything else is standard library.
- Dev tools, pinned in `requirements-dev.txt` at the latest PyPI versions: ruff 0.17.6,
  mypy 2.4.1, pytest 9.2.0, pytest-cov 7.1.0, pre-commit 4.7.0, import-linter 2.17, pip-audit 2.10.1,
  detect-secrets 1.5.0.
- Packaging: setuptools; discovery covers `src/support_agent` and the root `mock_env`
  package including its seed JSON (verified with a wheel build).

## 3. Folder tree (maps the Architecture bar)

This is the tree planned at P3. The as-built module list is in docs/design.md §3, which wins wherever the two differ.

```
mock_env/                     scaffolding from P2: read-only seed, in-memory runtime records, reset
  seed/*.json                 immutable seed customers and orders
  store.py, test_smoke.py     MockCommerceEnv; the four infrastructure smoke checks only
src/support_agent/
  domain/                     pure types; imports nothing outside the standard library
    money.py                  Money value object (Decimal + currency), rounding rules
    ids.py                    CustomerId, OrderId, ItemId, TraceId value objects
    orders.py                 Order, OrderLine, Shipping as frozen dataclasses with status enums
    refunds.py                RefundRecord and the refund state machine (allowed transitions)
    decisions.py              Decision kind and ReasonCode enums, Decision value
    turn.py                   SupportRequest, TurnResult, ProposedAction, Escalation
  policy/                     pure functions; no I/O
    rules.py                  small Specification-style rules, each returning a Decision
    engine.py                 PolicyEngine: runs the rules for one tool call, first non-allow wins
    refund_amounts.py         refundable amount computed from records (Decimal, cumulative cap)
  application/                depends only on ports
    ports.py                  OrderRepository, RefundRepository, ModelClient, AuditLog protocols
    context.py                ContextBuilder: loads only the authenticated customer's data
    tools.py                  tool command objects, registry, JSON schemas from typed arguments
    confirmations.py          pending confirmation store: single-use, bound to exact parameters
    orchestrator.py           bounded model/tool loop, propose/confirm, failure handling
    output_check.py           narrow reply check: no foreign data, no unsupported amount
    prompts.py                versioned system prompt
    service.py                SupportService facade: one request in, exactly one TurnResult out
  adapters/                   everything that touches the outside world
    mock_env_repository.py    customer-scoped repositories over MockCommerceEnv
    heuristic_model.py        mock ModelClient (generic intent/entity extraction, no store access)
    scripted_model.py         scripted fake ModelClient for fault injection and tests
    audit_log.py              append-only in-memory audit log keyed by trace_id
  composition.py              single composition root; MODEL_PROVIDER picks the model client
  cli.py                      `ask` and `run-scenarios` commands (UTF-8 I/O)
  harness.py                  scenario runner: reset, run turns, assert structural expectations
data/
  scenarios.json              the four example requests, unchanged
  expectations.json           structural assertions per scenario (plus labelled follow-up turns)
tests/                        unit tests per layer, fault tests, altered-seed pipeline test
scripts/check.py              ruff check, ruff format --check, mypy --strict, pytest with coverage
docs/                         brief, decisions, analysis, design
```

These are the planned modules. P5 can still merge or split them and will record any change in
docs/design.md.

## 4. Tooling (as built)

- `python -m scripts.check` runs 8 steps in order and stops at the first failure:
  1. ruff check;
  2. ruff format --check;
  3. import contracts (import-linter, ADR-5);
  4. mypy --strict on `src/` (pydantic plugin enabled; `mock_env/`, `scripts/` and `tests/` are not type-checked);
  5. pytest with coverage over `src/` and `mock_env/`;
  6. the coverage gate: always on, `COVERAGE_THRESHOLD = 85` on domain, policy and application;
  7. the secret scan (detect-secrets plus credential patterns, transcripts included, ADR-14);
  8. the dependency audit (pip-audit, ADR-7).
- pytest collects `tests/` and `mock_env/`.
- Ruff rules (ADR-6): F E W I UP B C4 SIM T20 RUF C90 N PT RET PIE ERA S BLE TRY ARG DTZ PLR0912 PLR0913 PLR2004,
  line length 120, max complexity 8. Per-file ignores: T20 for `src/support_agent/cli.py`; S101 and PLR2004 in
  `tests/` and the mock_env tests.
- `.pre-commit-config.yaml` has local `language: system` hooks (`python -m ruff`, `python -m mypy`,
  `python -m pytest`). They require the activated `.venv`.
- `.gitattributes` uses LF endings. `.gitignore` covers .venv, caches (including `.import_linter_cache/`), .env,
  `.claude/settings.local.json`, `*.zip` and `claude-transcripts/`.
- `.env.example` documents `MODEL_PROVIDER` (default `mock`). Only real environment variables are read;
  `ANTHROPIC_API_KEY` is reserved for a future provider and not read today.
- Packaging: `python -m scripts.package` (stdlib only) regenerates `claude-transcripts/INDEX.md` and builds the
  submission zip in `dist/` next to the project folder.

## 5. ADR list

The decision records live in [docs/adr/](adr/README.md), one file per decision (ADR-1 to ADR-14).

## 6. Security and governance additions (after the P8 reviews)

- **Policy version in every audit record** (ADR-13): each `AuditEntry` carries `prompt_version`, `policy_version` (from `config/policy.json`) and `model_id`. A test asserts it on every record.
- **Threat model** ([threat-model.md](threat-model.md)): OWASP Top 10 for LLM Applications (2025) mapped to controls, proving tests and open items. It is linked from the README and production-architecture.md.
- **Secret scan** (ADR-14): `detect-secrets` over source, config and docs, plus credential patterns over the same files and `claude-transcripts/`, as a `scripts.check` step that runs without git.
- **Quality gate order:** ruff check, ruff format, import contracts, mypy, pytest, coverage gate (85% on domain, policy and application), secret scan, dependency audit.

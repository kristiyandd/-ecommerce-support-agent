# ADR-14: Secret scan in the quality gate

Status: accepted (2026-11-23)

## Context
API keys may appear in source, config or docs while working with real providers. Git hooks do not exist before the repository is initialised.

## Decision
`scripts/secret_scan.py` runs `detect-secrets` (pinned) plus credential patterns (`sk-ant-`, `sk-`, `AKIA`, `ghp_`, Slack tokens, private-key headers) over an explicit file list (src, tests, scripts, mock_env, config, data, docs and root config files), so it works without git. It is a step of `scripts.check` and exits non-zero on any finding.

## Alternatives considered
A git pre-commit hook only (it would not run before `git init`, and is skipped by `--no-verify`).

## Consequences
A planted key fails the check (tested). The transcripts in `claude-transcripts/` are scanned with the credential patterns only, because their message signatures and IDs would flood the entropy check. Two documented fake keys typed during this session are allowlisted by exact value.

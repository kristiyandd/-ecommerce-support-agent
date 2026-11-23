"""Command line: `ask` runs one or more turns for a customer; `run-scenarios` runs the evaluation harness."""

import argparse
import io
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from mock_env import SEED_DIR, MockCommerceEnv
from support_agent.adapters.audit_log import InMemoryAuditLog
from support_agent.adapters.policy_file import PolicyFileError
from support_agent.composition import (
    MOCK_PROVIDER,
    PROVIDER_VARIABLE,
    UnknownProviderError,
    build_service,
    create_model,
    uuid_ids,
)
from support_agent.domain.ids import ConversationId, CustomerId
from support_agent.domain.turn import SupportRequest, TurnResult
from support_agent.evaluation import (
    DEFAULT_ADVERSARIAL,
    render_markdown,
    render_summary,
    run_adversarial,
    summary_payload,
)
from support_agent.harness import DEFAULT_EXPECTATIONS, DEFAULT_SCENARIOS, render_table, report_payload, run_harness

USAGE_ERROR = 2
MESSAGE_FILE_ENCODING = "utf-8-sig"  # accepts files saved with a byte-order mark (Notepad, PowerShell 5.1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="support_agent", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ask = commands.add_parser("ask", help="send one or more messages as an authenticated customer")
    ask.add_argument("--customer", required=True, help="authenticated customer ID, e.g. CUST-001")
    ask.add_argument("--message", action="append", default=[], help="a message; repeat for several turns")
    ask.add_argument("--message-file", type=Path, help="UTF-8 file with one message per line")
    ask.add_argument("--conversation", default="cli", help="conversation ID (default: cli)")
    scenarios = commands.add_parser("run-scenarios", help="run data/scenarios.json against data/expectations.json")
    scenarios.add_argument("--json", action="store_true", help="print JSON instead of a table")
    scenarios.add_argument("--report", type=Path, help="also write a Markdown evaluation report to this path")
    return parser


def _messages(arguments: argparse.Namespace) -> list[str]:
    messages: list[str] = list(arguments.message)
    if arguments.message_file is not None:
        text = arguments.message_file.read_text(encoding=MESSAGE_FILE_ENCODING)
        messages.extend(line.strip() for line in text.splitlines() if line.strip())
    return messages


def _describe(result: TurnResult) -> str:
    decisions = ", ".join(decision.label() for decision in result.decisions)
    parts = [f"trace={result.trace_id}", f"tools=[{', '.join(result.tool_calls)}]", f"decisions=[{decisions}]"]
    if result.proposal is not None:
        parts.append("proposal=pending confirmation")
    parts.extend(f"action={action.state}:{action.amount.format()}" for action in result.actions)
    if result.escalation is not None:
        parts.append(f"escalation=[{result.escalation.reason_labels()}]")
    return "  ".join(parts)


def _ask(arguments: argparse.Namespace) -> int:
    messages = _messages(arguments)
    if not messages:
        print("ask: give at least one --message or --message-file", file=sys.stderr)
        return USAGE_ERROR
    model = create_model(os.environ.get(PROVIDER_VARIABLE, MOCK_PROVIDER))
    service = build_service(MockCommerceEnv(), model, audit_log=InMemoryAuditLog(), new_id=uuid_ids())
    for message in messages:
        request = SupportRequest(CustomerId(arguments.customer), ConversationId(arguments.conversation), message)
        result = service.handle(request)
        print(f"customer> {message}\nassistant> {result.reply}\n  [{_describe(result)}]\n")
    return 0


def _run_scenarios(arguments: argparse.Namespace) -> int:
    provider = os.environ.get(PROVIDER_VARIABLE, MOCK_PROVIDER)
    report = run_harness(SEED_DIR, DEFAULT_SCENARIOS, DEFAULT_EXPECTATIONS, lambda: create_model(provider))
    adversarial = run_adversarial(SEED_DIR, DEFAULT_ADVERSARIAL, lambda: create_model(provider))
    if arguments.json:
        payload = {"scenarios": report_payload(report), "adversarial": summary_payload(adversarial)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_table(report))
        print(render_summary(adversarial))
    if arguments.report is not None:
        markdown = render_markdown(render_table(report), report.passed, adversarial, create_model(provider).model_id)
        arguments.report.write_text(markdown, encoding="utf-8")
    return 0 if report.passed and adversarial.passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    arguments = _parser().parse_args(argv)
    try:
        return _ask(arguments) if arguments.command == "ask" else _run_scenarios(arguments)
    except (UnknownProviderError, PolicyFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return USAGE_ERROR

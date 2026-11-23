"""Scenario harness: fresh environment and service per scenario, invariant and behaviour checks, reports."""

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mock_env import MockCommerceEnv
from support_agent.adapters.audit_log import InMemoryAuditLog
from support_agent.adapters.mock_env_data import REFUNDS_COLLECTION
from support_agent.application.ports import ModelClient
from support_agent.application.replies import NONE_LABEL
from support_agent.application.service import SupportService
from support_agent.composition import build_service, counter_ids
from support_agent.domain.ids import ConversationId, CustomerId
from support_agent.domain.turn import SupportRequest, TurnResult
from support_agent.harness_checks import (
    Observation,
    SeedFacts,
    check_final_refunds,
    check_first_turn,
    check_invariants,
    load_seed_facts,
    read_json,
)
from support_agent.paths import DATA_DIR

DEFAULT_SCENARIOS = DATA_DIR / "scenarios.json"
DEFAULT_EXPECTATIONS = DATA_DIR / "expectations.json"
REPLY_WIDTH = 70
TABLE_HEADERS = ("scenario", "turn", "reply", "tools", "decisions", "escalation", "state change", "result")
FIRST_TURN_LABEL = "request"

type Raw = Mapping[str, Any]


@dataclass(frozen=True)
class TurnReport:
    scenario_id: str
    turn_label: str
    reply: str
    tools: tuple[str, ...]
    decisions: tuple[str, ...]
    state_change: str
    escalation: str
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class HarnessReport:
    turns: tuple[TurnReport, ...]

    @property
    def passed(self) -> bool:
        return all(turn.passed for turn in self.turns)


def _state_change(before: int, refunds: tuple[Raw, ...]) -> str:
    new = refunds[before:]
    if not new:
        return NONE_LABEL
    return "; ".join(f"refund {refund['state']} {refund['item_id']} x{refund['quantity']}" for refund in new)


def _escalation_label(result: TurnResult) -> str:
    return NONE_LABEL if result.escalation is None else result.escalation.reason_labels()


def _with_failures(report: TurnReport, extra: list[str]) -> TurnReport:
    return TurnReport(
        report.scenario_id,
        report.turn_label,
        report.reply,
        report.tools,
        report.decisions,
        report.state_change,
        report.escalation,
        (*report.failures, *extra),
    )


class _ScenarioRun:
    """One scenario: reset state, play the turns, collect reports."""

    def __init__(self, seed_dir: Path, facts: SeedFacts, model: ModelClient, scenario: Raw) -> None:
        self._facts = facts
        self._scenario = scenario
        self._env = MockCommerceEnv(seed_dir)
        self._service: SupportService = build_service(
            self._env, model, audit_log=InMemoryAuditLog(), new_id=counter_ids()
        )
        self._messages: list[str] = []

    def refunds(self) -> tuple[Raw, ...]:
        return tuple(self._env.records(REFUNDS_COLLECTION))

    def turn(self, label: str, message: str, declared: object) -> tuple[TurnReport, TurnResult]:
        before = len(self.refunds())
        customer = str(self._scenario["authenticated_customer_id"])
        scenario_id = str(self._scenario["scenario_id"])
        self._messages.append(message)
        request = SupportRequest(CustomerId(customer), ConversationId(scenario_id), message)
        result = self._service.handle(request)
        refunds = self.refunds()
        observation = Observation(customer, tuple(self._messages), result, refunds, len(self._messages) == 1)
        report = TurnReport(
            scenario_id,
            label,
            result.reply,
            tuple(result.tool_calls),
            tuple(decision.label() for decision in result.decisions),
            _state_change(before, refunds),
            _escalation_label(result),
            tuple(check_invariants(observation, self._facts, declared)),
        )
        return report, result


def _run_scenario(
    seed_dir: Path, facts: SeedFacts, model: ModelClient, scenario: Raw, expected: Raw
) -> list[TurnReport]:
    run = _ScenarioRun(seed_dir, facts, model, scenario)
    behaviour: Raw = expected.get("behaviour", {})
    declared = expected.get("invariants", [])
    first, result = run.turn(FIRST_TURN_LABEL, str(scenario["message"]), declared)
    reports = [_with_failures(first, check_first_turn(result, behaviour.get("first_turn", {})))]
    follow = behaviour.get("follow_up")
    if follow:
        reports.append(run.turn(str(follow["label"]), str(follow["message"]), declared)[0])
    reports[-1] = _with_failures(reports[-1], check_final_refunds(run.refunds(), behaviour.get("final_refunds", [])))
    return reports


def _missing_expectations(scenario_id: str) -> TurnReport:
    failure = (f"no expectations for {scenario_id}",)
    return TurnReport(scenario_id, "-", "", (), (), NONE_LABEL, NONE_LABEL, failure)


def run_harness(
    seed_dir: Path,
    scenarios_path: Path,
    expectations_path: Path,
    model_factory: Callable[[], ModelClient],
) -> HarnessReport:
    facts = load_seed_facts(seed_dir)
    expectations: Raw = read_json(expectations_path)
    turns: list[TurnReport] = []
    for scenario in read_json(scenarios_path):
        expected = expectations.get(scenario["scenario_id"])
        if expected is None:
            turns.append(_missing_expectations(str(scenario["scenario_id"])))
        else:
            turns += _run_scenario(seed_dir, facts, model_factory(), scenario, expected)
    return HarnessReport(tuple(turns))


def _truncate(text: str, width: int = REPLY_WIDTH) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 3] + "..."


def _row(turn: TurnReport) -> tuple[str, ...]:
    outcome = "PASS" if turn.passed else "FAIL: " + "; ".join(turn.failures)
    return (
        turn.scenario_id,
        turn.turn_label,
        _truncate(turn.reply),
        ",".join(turn.tools) or "-",
        ",".join(turn.decisions) or "-",
        turn.escalation,
        turn.state_change,
        outcome,
    )


def render_table(report: HarnessReport) -> str:
    rows = [TABLE_HEADERS, *(_row(turn) for turn in report.turns)]
    widths = [max(len(row[column]) for row in rows) for column in range(len(TABLE_HEADERS))]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip() for row in rows]
    lines.insert(1, "  ".join("-" * width for width in widths))
    replies = [f"{turn.scenario_id} / {turn.turn_label}:\n  {turn.reply}" for turn in report.turns]
    return "\n".join([*lines, "", "Full replies:", *replies])


def report_payload(report: HarnessReport) -> dict[str, object]:
    return {"passed": report.passed, "turns": [{**asdict(turn), "passed": turn.passed} for turn in report.turns]}


def render_json(report: HarnessReport) -> str:
    return json.dumps(report_payload(report), ensure_ascii=False, indent=2)

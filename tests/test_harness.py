from collections.abc import Callable
from pathlib import Path

from mock_env import SEED_DIR
from support_agent.adapters.heuristic_model import HeuristicModel
from support_agent.adapters.scripted_model import ScriptedModel
from support_agent.application.model_protocol import ModelResponse
from support_agent.application.ports import ModelClient
from support_agent.harness import (
    DEFAULT_EXPECTATIONS,
    DEFAULT_SCENARIOS,
    HarnessReport,
    render_json,
    render_table,
    run_harness,
)

ALTERED = Path(__file__).parent / "fixtures" / "altered"


def _failures(report: HarnessReport) -> str:
    return "\n".join(f"{t.scenario_id}/{t.turn_label}: {t.failures}" for t in report.turns if not t.passed)


def _default_report() -> HarnessReport:
    return run_harness(SEED_DIR, DEFAULT_SCENARIOS, DEFAULT_EXPECTATIONS, HeuristicModel)


def _leaking_model() -> ModelClient:
    leak = ModelResponse(text="Your neighbour Martin Ivanov has this order.")
    return ScriptedModel([leak] * 4)


def test_default_scenarios_pass_with_heuristic_model() -> None:
    report = _default_report()
    assert report.passed, _failures(report)


def test_altered_seed_passes_with_heuristic_model() -> None:
    report = run_harness(ALTERED, ALTERED / "scenarios.json", ALTERED / "expectations.json", HeuristicModel)
    assert report.passed, _failures(report)


def test_harness_detects_leaked_foreign_data() -> None:
    report = run_harness(SEED_DIR, DEFAULT_SCENARIOS, DEFAULT_EXPECTATIONS, _leaking_model)
    assert not report.passed
    assert any("foreign data" in failure or "email" in failure for t in report.turns for failure in t.failures)


def test_renderers_mention_every_scenario() -> None:
    report = _default_report()
    table, payload = render_table(report), render_json(report)
    for turn in report.turns:
        assert turn.scenario_id in table
        assert turn.scenario_id in payload


def _replying(text: str) -> Callable[[], ModelClient]:
    return lambda: ScriptedModel([ModelResponse(text=text)] * 4)


def test_harness_detects_an_invented_delivery_date() -> None:
    report = run_harness(SEED_DIR, DEFAULT_SCENARIOS, DEFAULT_EXPECTATIONS, _replying("It arrives tomorrow."))

    assert any("date" in failure for turn in report.turns for failure in turn.failures)


def test_harness_detects_another_customers_order_amount() -> None:
    report = run_harness(SEED_DIR, DEFAULT_SCENARIOS, DEFAULT_EXPECTATIONS, _replying("That order was 129.00."))

    assert any("129.00" in failure for turn in report.turns for failure in turn.failures)

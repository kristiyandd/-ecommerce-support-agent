import json
from pathlib import Path

import pytest

from support_agent.adapters.policy_file import PolicyFileError
from support_agent.cli import main
from support_agent.composition import create_model
from support_agent.harness import DEFAULT_EXPECTATIONS


def test_ask_turns_share_one_conversation_so_yes_confirms(capsys: pytest.CaptureFixture[str]) -> None:
    refund = "One of the wine glasses in order ORD-200 arrived broken. Can I get a refund for it?"
    code = main(["ask", "--customer", "CUST-001", "--message", refund, "--message", "yes"])

    output = capsys.readouterr().out
    assert code == 0
    assert output.count("assistant>") == 2
    assert "action=issued" in output


def test_run_scenarios_exits_non_zero_when_an_expectation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expectations = json.loads(DEFAULT_EXPECTATIONS.read_text(encoding="utf-8"))
    expectations["scenario-01"]["behaviour"]["first_turn"]["tools_called"] = ["request_refund"]
    broken = tmp_path / "expectations.json"
    broken.write_text(json.dumps(expectations), encoding="utf-8")
    monkeypatch.setattr("support_agent.cli.DEFAULT_EXPECTATIONS", broken)

    assert main(["run-scenarios"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_ask_reads_messages_from_a_utf8_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    messages = tmp_path / "messages.txt"
    messages.write_text("Where is order ORD-100? €\n\n", encoding="utf-8")

    assert main(["ask", "--customer", "CUST-001", "--message-file", str(messages)]) == 0
    assert capsys.readouterr().out.count("assistant>") == 1


def test_ask_without_messages_is_a_usage_error() -> None:
    assert main(["ask", "--customer", "CUST-001"]) == 2


def test_run_scenarios_json_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run-scenarios", "--json"]) == 0
    assert "scenario-04" in capsys.readouterr().out


def test_unknown_model_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="MODEL_PROVIDER"):
        create_model("openai")


def test_run_scenarios_json_is_one_valid_document(capsys: pytest.CaptureFixture[str]) -> None:
    main(["run-scenarios", "--json"])

    document = json.loads(capsys.readouterr().out)
    assert {"scenarios", "adversarial"} <= document.keys()


def test_unknown_provider_is_a_clean_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "other")

    assert main(["ask", "--customer", "CUST-001", "--message", "hi"]) == 2
    assert "MODEL_PROVIDER" in capsys.readouterr().err


def test_message_file_with_a_byte_order_mark_is_read_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    messages = tmp_path / "messages.txt"
    messages.write_text("Where is order ORD-100?\n", encoding="utf-8-sig")

    main(["ask", "--customer", "CUST-001", "--message-file", str(messages)])

    assert "customer> Where is order ORD-100?" in capsys.readouterr().out


def test_a_broken_policy_file_is_a_clean_configuration_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken_policy() -> None:
        raise PolicyFileError("config/policy.json", "cannot be read as JSON")

    monkeypatch.setattr("support_agent.composition.load_policy_config", broken_policy)

    assert main(["ask", "--customer", "CUST-001", "--message", "hi"]) == 2
    assert "policy" in capsys.readouterr().err

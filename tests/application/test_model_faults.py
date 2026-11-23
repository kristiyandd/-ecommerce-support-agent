"""Model failures end in a safe TurnResult: no state change, no proposal, an audit entry."""

from collections.abc import Callable, Sequence

import pytest

from mock_env import MockCommerceEnv
from support_agent.adapters.audit_log import InMemoryAuditLog
from support_agent.adapters.scripted_model import ScriptedModel
from support_agent.application.audit import AuditKind
from support_agent.application.model_protocol import ModelResponse, ToolCall
from support_agent.application.replies import CLARIFY
from support_agent.composition import build_service
from support_agent.domain.decisions import ReasonCode
from support_agent.domain.ids import ConversationId, CustomerId
from support_agent.domain.turn import SupportRequest, TurnResult

CUSTOMER = CustomerId("CUST-001")


def _call(name: str, arguments_json: str) -> ModelResponse:
    return ModelResponse(text=None, tool_calls=(ToolCall("call-1", name, arguments_json),))


def _run(
    env: MockCommerceEnv,
    audit_log: InMemoryAuditLog,
    ids: Callable[[], str],
    script: Sequence[ModelResponse | Exception],
) -> TurnResult:
    service = build_service(env, ScriptedModel(script), audit_log=audit_log, new_id=ids)
    return service.handle(SupportRequest(CUSTOMER, ConversationId("conv-1"), "I need help with my order"))


FAULT_AUDIT_KINDS = frozenset({AuditKind.DECISION, AuditKind.MODEL_ERROR})


def _assert_safe(result: TurnResult, env: MockCommerceEnv, audit_log: InMemoryAuditLog) -> None:
    assert env.records("refunds") == []
    assert result.proposal is None
    assert result.actions == ()
    assert result.reply.strip()
    assert any(entry.kind in FAULT_AUDIT_KINDS for entry in audit_log.entries(result.trace_id))


def _assert_clarifies_or_escalates(result: TurnResult, expected: ReasonCode) -> None:
    escalates = expected in {ReasonCode.LOOP_EXHAUSTED, ReasonCode.MODEL_UNAVAILABLE}
    if escalates:
        assert result.escalation is not None
        assert expected in result.escalation.reasons
    else:
        assert result.escalation is None
        assert result.reply == CLARIFY


def _reasons(result: TurnResult) -> set[ReasonCode]:
    escalated = set(result.escalation.reasons) if result.escalation else set()
    return {decision.reason for decision in result.decisions} | escalated


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ([_call("request_refund", "{not json")], ReasonCode.INVALID_ARGUMENTS),
        ([_call("request_refund", '{"order_id": "ORD-200"}')], ReasonCode.INVALID_ARGUMENTS),
        ([_call("issue_payment", "{}")], ReasonCode.UNKNOWN_TOOL),
        ([_call("get_order", '{"order_id": "ORD-100"}')] * 10, ReasonCode.LOOP_EXHAUSTED),
        ([TimeoutError("provider timed out")], ReasonCode.MODEL_UNAVAILABLE),
    ],
    ids=["malformed-json", "missing-arguments", "unknown-tool", "loop-exhaustion", "provider-error"],
)
def test_model_fault_ends_in_a_safe_result(
    env: MockCommerceEnv,
    audit_log: InMemoryAuditLog,
    counter_ids: Callable[[], str],
    script: Sequence[ModelResponse | Exception],
    expected: ReasonCode,
) -> None:
    result = _run(env, audit_log, counter_ids, script)

    _assert_safe(result, env, audit_log)
    assert expected in _reasons(result)
    _assert_clarifies_or_escalates(result, expected)


def test_foreign_order_is_reported_as_not_found_and_never_refunded(
    env: MockCommerceEnv, audit_log: InMemoryAuditLog, counter_ids: Callable[[], str]
) -> None:
    foreign = next(str(raw["order_id"]) for raw in env.orders() if raw["customer_id"] != CUSTOMER)
    foreign_item = next(str(raw["items"][0]["item_id"]) for raw in env.orders() if raw["order_id"] == foreign)
    refund_args = f'{{"order_id": "{foreign}", "item_id": "{foreign_item}", "quantity": 1, "reason": "damaged"}}'
    script = [
        _call("get_order", f'{{"order_id": "{foreign}"}}'),
        _call("request_refund", refund_args),
        ModelResponse(text="I could not find that order on your account."),
    ]

    result = _run(env, audit_log, counter_ids, script)

    _assert_safe(result, env, audit_log)
    assert ReasonCode.ORDER_NOT_FOUND in _reasons(result)
    tool_payloads = " ".join(entry.payload.get("result", "") for entry in audit_log.entries(result.trace_id))
    assert "CUST-002" not in tool_payloads
    assert '"found": false' in tool_payloads


def test_every_audit_record_carries_prompt_policy_and_model_versions(
    env: MockCommerceEnv, audit_log: InMemoryAuditLog, counter_ids: Callable[[], str]
) -> None:
    result = _run(env, audit_log, counter_ids, [ModelResponse(text="Hello")])

    entries = audit_log.entries(result.trace_id)
    assert entries
    stamps = {(entry.prompt_version, entry.policy_version, entry.model_id) for entry in entries}
    assert stamps == {("support-agent/v1", "policy/v1", "scripted-fake")}

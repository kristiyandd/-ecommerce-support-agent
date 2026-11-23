"""Safety properties of whole turns found in the P8 review: money wording, claims, attribution, failures."""

from collections.abc import Callable

import pytest

from mock_env import MockCommerceEnv
from support_agent.adapters.audit_log import InMemoryAuditLog
from support_agent.adapters.heuristic_model import HeuristicModel
from support_agent.adapters.scripted_model import ScriptedModel
from support_agent.application.audit import AuditEntry
from support_agent.application.model_protocol import ModelResponse, ToolCall
from support_agent.application.ports import ModelClient
from support_agent.application.service import SupportService
from support_agent.composition import build_service
from support_agent.domain.decisions import ReasonCode
from support_agent.domain.ids import ConversationId, CustomerId
from support_agent.domain.turn import SupportRequest, TurnResult

CUSTOMER = CustomerId("CUST-001")
GLASS = '{"order_id": "ORD-200", "item_id": "ITEM-201", "quantity": 1, "reason": "damaged"}'


def _service(env: MockCommerceEnv, ids: Callable[[], str], model: ModelClient | None = None) -> SupportService:
    return build_service(env, model or HeuristicModel(), audit_log=InMemoryAuditLog(), new_id=ids)


def _say(service: SupportService, message: str, conversation: str = "c1") -> TurnResult:
    return service.handle(SupportRequest(CUSTOMER, ConversationId(conversation), message))


def _reasons(result: TurnResult) -> set[ReasonCode]:
    escalated = set(result.escalation.reasons) if result.escalation else set()
    return {decision.reason for decision in result.decisions} | escalated


def _scripted_reply(env: MockCommerceEnv, ids: Callable[[], str], text: str) -> TurnResult:
    script = [ModelResponse(None, (ToolCall("call-1", "request_refund", GLASS),)), ModelResponse(text)]
    return _say(_service(env, ids, ScriptedModel(script)), "help")


@pytest.mark.parametrize(
    "text",
    [
        "You will get 500 EUR back.",
        "You will get 1,290.00 EUR back.",
        "You will receive 54.80 EUR back for the glass.",
        "Your money has been sent back.",
        "It has been re​funded.",
        "Order ord-204 is fine.",
        "Order ORD 204 is fine.",
    ],
    ids=["integer", "thousands", "other-record-amount", "sent-back", "zero-width", "lowercase-id", "spaced-id"],
)
def test_model_text_cannot_state_money_outcomes_or_foreign_ids(
    env: MockCommerceEnv, counter_ids: Callable[[], str], text: str
) -> None:
    result = _scripted_reply(env, counter_ids, text)

    assert ReasonCode.OUTPUT_BLOCKED in _reasons(result)
    assert result.proposal is None


def test_a_claim_without_decimals_still_triggers_the_dispute(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    result = _say(_service(env, counter_ids), "The decanter from ORD-200 arrived cracked, I paid €60 for it, refund")

    assert ReasonCode.AMOUNT_DISPUTE in _reasons(result)


def test_quoting_the_order_total_is_not_a_dispute(env: MockCommerceEnv, counter_ids: Callable[[], str]) -> None:
    result = _say(_service(env, counter_ids), "Total was 54.80. The decanter from ORD-200 is cracked, refund it")

    assert result.proposal is not None
    assert ReasonCode.AMOUNT_DISPUTE not in _reasons(result)


def test_a_number_unrelated_to_the_item_is_not_a_quantity(env: MockCommerceEnv, counter_ids: Callable[[], str]) -> None:
    result = _say(_service(env, counter_ids), "Refund the wine glass from ORD-200, it broke 2 days ago")

    assert result.proposal is None or result.proposal.quantity == 1


def test_a_word_containing_person_is_not_a_request_for_a_human(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    result = _say(_service(env, counter_ids), "My personal order ORD-200: the decanter broke, refund please")

    assert ReasonCode.CUSTOMER_REQUESTED_HUMAN not in _reasons(result)
    assert result.proposal is not None


def test_a_customer_id_in_the_message_is_not_an_order_id(env: MockCommerceEnv, counter_ids: Callable[[], str]) -> None:
    result = _say(_service(env, counter_ids), "I'm CUST-001, the decanter in ORD-200 is cracked, refund it")

    assert result.proposal is not None


def test_dispute_is_attributed_to_its_own_item(env: MockCommerceEnv, counter_ids: Callable[[], str]) -> None:
    script = [
        ModelResponse(None, (ToolCall("call-1", "request_refund", GLASS),)),
        ModelResponse(None, (ToolCall("call-2", "escalate_to_human", "{}"),)),
        ModelResponse("ok"),
    ]
    service = _service(env, counter_ids, ScriptedModel(script))

    result = _say(service, "I paid 20.00 for the glass")

    assert result.escalation is not None
    assert "ITEM-201" in result.escalation.summary
    assert "14.90" in result.reply


def test_an_infrastructure_failure_still_returns_a_safe_result(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    env.append_record("refunds", {"customer_id": "CUST-001", "broken": True})

    result = _say(_service(env, counter_ids), "The decanter in ORD-200 is cracked, refund it")

    assert result.escalation is not None
    assert ReasonCode.INTERNAL_ERROR in result.escalation.reasons
    assert result.proposal is None


def test_replayed_confirmation_says_the_refund_already_exists(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    service = _service(env, counter_ids)
    message = "One wine glass in ORD-200 is broken, refund it"
    _say(service, message, "a")
    _say(service, message, "b")
    _say(service, "yes", "a")

    replay = _say(service, "yes", "b")

    assert "already" in replay.reply.lower()
    assert len(env.records("refunds")) == 1


class FailingAuditLog(InMemoryAuditLog):
    def __init__(self, failing_kind: str) -> None:
        super().__init__()
        self._failing_kind = failing_kind

    def append(self, entry: AuditEntry) -> None:
        if entry.kind == self._failing_kind:
            raise OSError(entry.kind)
        super().append(entry)


def _service_with_log(env: MockCommerceEnv, ids: Callable[[], str], log: InMemoryAuditLog) -> SupportService:
    return build_service(env, HeuristicModel(), audit_log=log, new_id=ids)


def test_ordered_count_is_not_taken_as_the_refund_quantity(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    message = "I ordered 2 wine glasses on ORD-200 and one arrived broken, refund please"

    result = _say(_service(env, counter_ids), message)

    assert result.proposal is None


def test_audit_failure_after_a_refund_still_reports_the_refund(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    service = _service_with_log(env, counter_ids, FailingAuditLog("action"))
    _say(service, "The decanter in ORD-200 is cracked, refund it")

    confirmed = _say(service, "yes")

    assert len(confirmed.actions) == 1
    assert "no money has moved" not in confirmed.reply


def test_audit_failure_on_the_result_still_returns_a_result(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    service = _service_with_log(env, counter_ids, FailingAuditLog("result"))

    result = _say(service, "Where is order ORD-100?")

    assert result.reply


def test_dispute_line_quotes_the_disputing_claim_not_the_order_total(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    message = "ORD-200 total was 54.80, the wine glass I paid 20.00 for broke, one wine glass refund please"

    result = _say(_service(env, counter_ids), message)

    assert "20.00 EUR" in result.reply
    assert "(54.80 EUR)" not in result.reply


def test_dispute_is_recorded_as_a_decision(env: MockCommerceEnv, counter_ids: Callable[[], str]) -> None:
    result = _say(_service(env, counter_ids), "The decanter from ORD-200 is cracked, I paid 60.00, refund it")

    assert ReasonCode.AMOUNT_DISPUTE in {decision.reason for decision in result.decisions}


def test_an_amount_in_another_currency_code_is_not_a_euro_dispute(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    result = _say(_service(env, counter_ids), "USD 80.00 for the decanter on ORD-200, it broke, refund please")

    assert ReasonCode.AMOUNT_DISPUTE not in _reasons(result)


def test_plural_item_name_with_a_quantity_is_understood(env: MockCommerceEnv, counter_ids: Callable[[], str]) -> None:
    result = _say(_service(env, counter_ids), "Refund the two glasses from ORD-200 please, they broke")

    assert result.proposal is not None
    assert result.proposal.quantity == 2


def test_a_negative_quantity_is_not_read_as_a_positive_one(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    result = _say(_service(env, counter_ids), "Refund -1 wine glasses from ORD-200, broken")

    assert result.proposal is None


def test_amount_dispute_summary_records_both_the_claim_and_the_record_amount(
    env: MockCommerceEnv, counter_ids: Callable[[], str]
) -> None:
    result = _say(_service(env, counter_ids), "The decanter from ORD-200 is cracked, I paid 60.00, refund it")

    assert result.escalation is not None
    assert "amount=25.00 EUR" in result.escalation.summary
    assert "claimed=60.00 EUR" in result.escalation.summary


def test_a_blocked_reply_is_audited_as_a_hash_not_as_text(env: MockCommerceEnv, counter_ids: Callable[[], str]) -> None:
    log = InMemoryAuditLog()
    service = build_service(
        env, ScriptedModel([ModelResponse("Order ORD-204 is yours")]), audit_log=log, new_id=counter_ids
    )

    result = _say(service, "help")

    blocked = [entry for entry in log.entries(result.trace_id) if entry.kind == "output_check"]
    assert blocked
    assert "reply_sha256" in blocked[0].payload
    assert all("ORD-204" not in value for entry in blocked for value in entry.payload.values())

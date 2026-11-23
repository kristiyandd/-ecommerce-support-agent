import json
import re

import pytest

from support_agent.adapters.heuristic_model import HeuristicModel
from support_agent.application.model_protocol import Message, ModelRequest, ModelResponse, Role, ToolCall

DECIMAL_AMOUNT = re.compile(r"\d+[.,]\d{2}")

GENERIC_ORDER_ID = r"\b[A-Z]{2,5}-\d+\b"


def order(*lines: tuple[str, str, int], status: str = "delivered", shipping: bool = False) -> dict[str, object]:
    return {
        "found": True,
        "order_id": "SHP-7",
        "status": status,
        "shipping": {"carrier": "UPS", "tracking_number": "TRK-1"} if shipping else None,
        "lines": [
            {"item_id": item_id, "name": name, "quantity": quantity, "unit_price": "9.99", "refunded_quantity": 0}
            for item_id, name, quantity in lines
        ],
    }


LAMP = ("I-1", "Desk Lamp", 1)
GLASS = ("I-2", "Wine Glass", 4)
CHAIR = ("I-3", "Office Chair", 1)


def request(text: str, *steps: tuple[str, dict[str, object]]) -> ModelRequest:
    messages = [Message(Role.USER, text)]
    for index, (name, payload) in enumerate(steps, start=1):
        call_id = f"call-{index}"
        messages.append(Message(Role.ASSISTANT, "", tool_calls=(ToolCall(call_id, name, "{}"),)))
        messages.append(Message(Role.TOOL, json.dumps({"untrusted_data": payload}), tool_call_id=call_id))
    return ModelRequest("system", tuple(messages), ())


def complete(text: str, *steps: tuple[str, dict[str, object]]) -> ModelResponse:
    return HeuristicModel(GENERIC_ORDER_ID).complete(request(text, *steps))


def only_call(response: ModelResponse) -> tuple[str, dict[str, object]]:
    assert response.text is None
    assert len(response.tool_calls) == 1
    return response.tool_calls[0].name, json.loads(response.tool_calls[0].arguments_json)


def test_status_first_asks_for_order() -> None:
    response = complete("Where is my order SHP-7?")
    assert only_call(response) == ("get_order", {"order_id": "SHP-7"})
    assert response.tool_calls[0].call_id == "call-1"


def test_status_reply_with_shipping() -> None:
    reply = complete("Where is my order SHP-7?", ("get_order", order(LAMP, status="in_transit", shipping=True))).text
    assert reply is not None
    assert "Order SHP-7 is in transit" in reply
    assert "UPS" in reply
    assert "TRK-1" in reply
    assert "I don't have a delivery estimate on file." in reply


def test_status_reply_without_shipping() -> None:
    reply = complete("status of SHP-7", ("get_order", order(LAMP))).text
    assert reply is not None
    assert reply.startswith("Order SHP-7 is delivered.")


def test_not_found_reply_for_status_and_refund_without_refund_call() -> None:
    for text in ("track SHP-7", "refund SHP-7 please"):
        response = complete(text, ("get_order", {"found": False}))
        assert response.tool_calls == ()
        assert response.text == "I can't find order SHP-7 on your account."


def test_refund_single_line_with_quantity_one() -> None:
    name, arguments = only_call(complete("I want a refund for SHP-7, it arrived broken", ("get_order", order(LAMP))))
    assert name == "request_refund"
    assert arguments == {"order_id": "SHP-7", "item_id": "I-1", "quantity": 1, "reason": "damaged"}


def test_refund_call_id_counts_tool_messages() -> None:
    response = complete("refund SHP-7", ("get_order", order(LAMP)))
    assert response.tool_calls[0].call_id == "call-2"


def test_refund_matches_item_by_name_with_plural() -> None:
    lines = (LAMP, GLASS, CHAIR)
    name, arguments = only_call(complete("refund 2 wine glasses from SHP-7", ("get_order", order(*lines))))
    assert name == "request_refund"
    assert arguments["item_id"] == "I-2"
    assert arguments["quantity"] == 2


def test_quantity_word_and_returned_reason() -> None:
    _, arguments = only_call(complete("I returned three desk lamps, refund SHP-7", ("get_order", order(LAMP, CHAIR))))
    assert arguments["quantity"] == 3
    assert arguments["reason"] == "returned"


def test_reason_defaults_to_other() -> None:
    _, arguments = only_call(complete("refund SHP-7, changed my mind", ("get_order", order(LAMP))))
    assert arguments["reason"] == "other"


def test_quantity_not_taken_from_ids_or_amounts() -> None:
    lines = (LAMP, GLASS)
    response = complete("refund the wine glass from SHP-7, I paid 34.90 EUR", ("get_order", order(*lines)))
    assert response.text == "How many of that item would you like a refund for?"
    assert response.tool_calls == ()


def test_missing_quantity_on_multi_unit_line_clarifies() -> None:
    response = complete("refund the wine glass in SHP-7", ("get_order", order(GLASS, LAMP)))
    assert response.text is not None
    assert response.tool_calls == ()


def test_no_item_match_or_several_clarify() -> None:
    lines = (LAMP, GLASS)
    assert complete("refund the toaster in SHP-7", ("get_order", order(*lines))).text == (
        "Which item from the order is this about?"
    )
    two_lamps = (("I-1", "Desk Lamp", 1), ("I-9", "Floor Lamp", 1))
    assert complete("refund the lamp in SHP-7", ("get_order", order(*two_lamps))).tool_calls == ()


@pytest.mark.parametrize("text", ["refund please", "refund SHP-7 and SHP-8"])
def test_order_id_must_be_exactly_one(text: str) -> None:
    response = complete(text)
    assert response.tool_calls == ()
    assert response.text == "Which order do you mean? Please send me exactly one order ID."


def test_human_calls_escalation_then_replies() -> None:
    assert only_call(complete("let me talk to a human")) == ("escalate_to_human", {})
    reply = complete("let me talk to a human", ("escalate_to_human", {"escalated": True})).text
    assert reply == ""


def test_precedence_refund_over_status() -> None:
    name, _ = only_call(complete("my parcel arrived damaged, refund please SHP-7", ("get_order", order(LAMP))))
    assert name == "request_refund"


def test_precedence_human_over_refund() -> None:
    name, _ = only_call(complete("I want a refund and a manager for SHP-7"))
    assert name == "escalate_to_human"


@pytest.mark.parametrize("text", ["hello there", "thanks", ""])
def test_unclear_makes_no_tool_call(text: str) -> None:
    response = complete(text)
    assert response.tool_calls == ()
    assert response.text


def test_only_current_turn_is_read() -> None:
    history = (
        Message(Role.USER, "let me talk to a human"),
        Message(Role.ASSISTANT, "done"),
        Message(Role.USER, "where is SHP-7"),
    )
    response = HeuristicModel(GENERIC_ORDER_ID).complete(ModelRequest("system", history, ()))
    assert only_call(response)[0] == "get_order"


DECISIONS: list[tuple[dict[str, object], str]] = [
    (
        {
            "decision": "needs_confirmation",
            "reason_code": "confirmation_required",
            "amount": "9.99 EUR",
            "item_name": "Desk Lamp",
            "quantity": 1,
        },
        "I can offer a refund for 1 \u00d7 Desk Lamp from order SHP-7.",
    ),
    ({"decision": "escalate", "reason_code": "above_approval_threshold"}, ""),
    ({"decision": "deny", "reason_code": "already_refunded"}, ""),
    ({"decision": "deny", "reason_code": "something_new"}, ""),
    ({"unexpected": True}, ""),
]


@pytest.mark.parametrize(("result", "expected"), DECISIONS)
def test_refund_replies_from_tool_result(result: dict[str, object], expected: str) -> None:
    reply = complete("refund SHP-7", ("get_order", order(LAMP)), ("request_refund", result)).text
    assert reply is not None
    assert reply.startswith(expected)
    assert DECIMAL_AMOUNT.search(reply) is None
    assert not re.search(r"refunded|processed|issued", reply.replace("already been refunded", ""))


def test_garbled_tool_payload_is_tolerated() -> None:
    messages = (
        Message(Role.USER, "where is SHP-7"),
        Message(Role.ASSISTANT, "", tool_calls=(ToolCall("call-1", "get_order", "{}"),)),
        Message(Role.TOOL, "not json", tool_call_id="call-1"),
    )
    response = HeuristicModel(GENERIC_ORDER_ID).complete(ModelRequest("system", messages, ()))
    assert response.text == "I can't find order SHP-7 on your account."


def test_status_question_without_an_order_id_lists_the_customers_orders() -> None:
    assert only_call(complete("where is my parcel")) == ("list_my_orders", {})

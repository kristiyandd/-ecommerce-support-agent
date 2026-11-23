import pytest

from support_agent.application.config import OrchestratorConfig
from support_agent.application.output_check import AllowedFacts, OutputCheck
from support_agent.domain.decisions import ReasonCode

ALLOWED = AllowedFacts(order_ids=frozenset({"ORD-1"}), refund_on_record=False, item_names=frozenset())


def _check(reply: str, allowed: AllowedFacts = ALLOWED) -> ReasonCode | None:
    return OutputCheck(OrchestratorConfig()).check(reply, allowed)


@pytest.mark.parametrize(
    "reply",
    [
        "Order ORD-2 is on its way.",
        "Order ord-2 is late.",
        "Order ORD" + chr(0x2011) + "2 is late.",
        "Write to someone@example.test for details.",
        "It will arrive on 2026-12-01.",
        "You will get 12.00 EUR back.",
        "You will get 12 EUR back.",
        "That costs €12.",
        "Your refund has been processed.",
        "It has been re​funded.",
        "The money was credited.",
        "I can refund EUR 60 for that.",
        "We can give you 60 dollars back.",
        "You get sixty euros back.",
        "Your refund has been approved.",
        "Your refund is complete.",
        "You will get 1,290.00 back.",
    ],
    ids=[
        "foreign-order",
        "foreign-order-lowercase",
        "foreign-order-unicode-hyphen",
        "email",
        "date",
        "decimal-amount",
        "whole-amount",
        "euro-sign",
        "invented-outcome",
        "zero-width-outcome",
        "credited",
        "currency-code-prefix",
        "dollars",
        "spelled-out",
        "approved",
        "complete",
        "thousands",
    ],
)
def test_unsafe_model_text_is_blocked(reply: str) -> None:
    assert _check(reply) is ReasonCode.OUTPUT_BLOCKED


def test_text_using_only_allowed_facts_passes() -> None:
    assert _check("Order ORD-1 has one item; tracking DHL-ORD100-TEST.") is None


def test_stating_what_can_still_be_refunded_is_not_an_invented_outcome() -> None:
    assert _check("That's more units than can still be refunded.") is None


def test_a_completed_refund_may_be_mentioned_when_the_records_show_one() -> None:
    allowed = AllowedFacts(ALLOWED.order_ids, refund_on_record=True, item_names=frozenset())

    assert _check("That item has already been refunded.", allowed) is None


def test_order_ids_are_compared_in_canonical_form() -> None:
    check = OutputCheck(OrchestratorConfig())

    assert check.canonical_order_ids("see ord 12 and ORD-13") == frozenset({"ORD-12", "ORD-13"})


@pytest.mark.parametrize(
    "reply", ["It is expected on 24.11. at the depot.", "I can offer a refund for 1 x 10 Euro Gift Card."]
)
def test_dates_and_known_item_names_are_not_money(reply: str) -> None:
    allowed = AllowedFacts(ALLOWED.order_ids, refund_on_record=False, item_names=frozenset({"10 Euro Gift Card"}))

    assert _check(reply, allowed) is None

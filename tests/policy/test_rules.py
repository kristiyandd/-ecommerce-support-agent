from collections.abc import Callable

import pytest

from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import ItemId
from support_agent.domain.orders import OrderStatus
from support_agent.domain.refunds import RefundState
from support_agent.policy.config import PolicyConfig
from support_agent.policy.rules import (
    RULES,
    RefundCheck,
    amount_dispute,
    approval_threshold,
    confirmation_required,
    customer_cap,
    item_on_order,
    order_cap,
    order_in_scope,
    order_status_eligible,
    quantity_within_refundable,
    something_left_to_refund,
)

from .conftest import build_order, build_record, eur

CheckFactory = Callable[..., RefundCheck]
RuleFn = Callable[[RefundCheck, PolicyConfig], Decision | None]


def test_order_in_scope_denies_a_missing_order(check_factory: CheckFactory, config: PolicyConfig) -> None:
    assert order_in_scope(check_factory(None), config) == Decision(DecisionKind.DENY, ReasonCode.ORDER_NOT_FOUND)


def test_order_in_scope_passes_for_a_found_order(check_factory: CheckFactory, config: PolicyConfig) -> None:
    assert order_in_scope(check_factory(build_order()), config) is None


@pytest.mark.parametrize("status", [OrderStatus.IN_TRANSIT, OrderStatus.UNKNOWN])
def test_status_rule_denies_ineligible_statuses(
    status: OrderStatus, check_factory: CheckFactory, config: PolicyConfig
) -> None:
    decision = order_status_eligible(check_factory(build_order(status=status)), config)

    assert decision == Decision(DecisionKind.DENY, ReasonCode.ORDER_NOT_ELIGIBLE)


@pytest.mark.parametrize("status", [OrderStatus.DELIVERED, OrderStatus.RETURNED])
def test_status_rule_passes_refundable_statuses(
    status: OrderStatus, check_factory: CheckFactory, config: PolicyConfig
) -> None:
    assert order_status_eligible(check_factory(build_order(status=status)), config) is None


def test_item_rule_denies_an_item_not_on_the_order(check_factory: CheckFactory, config: PolicyConfig) -> None:
    decision = item_on_order(check_factory(build_order(), item_id=ItemId("nope")), config)

    assert decision == Decision(DecisionKind.DENY, ReasonCode.ITEM_NOT_ON_ORDER)


def test_item_rule_passes_for_an_item_on_the_order(check_factory: CheckFactory, config: PolicyConfig) -> None:
    assert item_on_order(check_factory(build_order()), config) is None


def test_nothing_left_denies_when_all_units_are_refunded(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(quantity=2), order_refunds=(build_record(quantity=2),))

    assert something_left_to_refund(check, config) == Decision(DecisionKind.DENY, ReasonCode.ALREADY_REFUNDED)


def test_nothing_left_passes_when_a_unit_remains(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(quantity=2), order_refunds=(build_record(quantity=1),))

    assert something_left_to_refund(check, config) is None


def test_pending_review_records_do_not_use_up_units(check_factory: CheckFactory, config: PolicyConfig) -> None:
    pending = build_record(quantity=2, state=RefundState.PENDING_REVIEW)
    check = check_factory(build_order(quantity=2), order_refunds=(pending,))

    assert something_left_to_refund(check, config) is None


def test_quantity_rule_denies_more_than_refundable(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(quantity=2), quantity=2, order_refunds=(build_record(quantity=1),))

    assert quantity_within_refundable(check, config) == Decision(
        DecisionKind.DENY, ReasonCode.QUANTITY_EXCEEDS_REFUNDABLE
    )


@pytest.mark.parametrize("quantity", [0, -1])
def test_quantity_rule_denies_quantities_below_one(
    quantity: int, check_factory: CheckFactory, config: PolicyConfig
) -> None:
    decision = quantity_within_refundable(check_factory(build_order(), quantity=quantity), config)

    assert decision == Decision(DecisionKind.DENY, ReasonCode.QUANTITY_EXCEEDS_REFUNDABLE)


def test_quantity_rule_passes_up_to_the_refundable_quantity(check_factory: CheckFactory, config: PolicyConfig) -> None:
    assert quantity_within_refundable(check_factory(build_order(quantity=2), quantity=2), config) is None


def test_order_cap_denies_when_refunds_would_exceed_the_total(
    check_factory: CheckFactory, config: PolicyConfig
) -> None:
    order = build_order(price="10.00", quantity=2, total="15.00")
    check = check_factory(order, quantity=1, order_refunds=(build_record("10.00"),))

    assert order_cap(check, config) == Decision(DecisionKind.DENY, ReasonCode.EXCEEDS_AMOUNT_PAID)


def test_order_cap_passes_when_refunds_equal_the_total(check_factory: CheckFactory, config: PolicyConfig) -> None:
    order = build_order(price="10.00", quantity=2, total="20.00")
    check = check_factory(order, quantity=1, order_refunds=(build_record("10.00"),))

    assert order_cap(check, config) is None


def test_threshold_escalates_above_it_with_the_amount(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(price="30.00", quantity=2), quantity=2)

    assert approval_threshold(check, config) == Decision(
        DecisionKind.ESCALATE, ReasonCode.ABOVE_APPROVAL_THRESHOLD, eur("60.00")
    )


def test_threshold_passes_at_exactly_the_threshold(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(price="25.00", quantity=2), quantity=2)

    assert approval_threshold(check, config) is None


def test_customer_cap_escalates_with_cumulative_total(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(price="30.00"), customer_refunds=(build_record("80.00"),))

    assert customer_cap(check, config) == Decision(
        DecisionKind.ESCALATE, ReasonCode.CUSTOMER_LIMIT_EXCEEDED, eur("30.00")
    )


def test_customer_cap_passes_at_exactly_the_cap(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(price="20.00"), customer_refunds=(build_record("80.00"),))

    assert customer_cap(check, config) is None


def test_customer_cap_ignores_records_that_are_not_issued(check_factory: CheckFactory, config: PolicyConfig) -> None:
    pending = build_record("500.00", state=RefundState.PENDING_REVIEW)

    assert customer_cap(check_factory(build_order(), customer_refunds=(pending,)), config) is None


@pytest.mark.parametrize(
    "rule",
    [
        order_status_eligible,
        item_on_order,
        something_left_to_refund,
        quantity_within_refundable,
        order_cap,
        approval_threshold,
        customer_cap,
    ],
)
def test_later_rules_defer_to_rule_one_when_the_order_is_missing(
    rule: RuleFn, check_factory: CheckFactory, config: PolicyConfig
) -> None:
    assert rule(check_factory(None), config) is None


@pytest.mark.parametrize(
    "rule", [something_left_to_refund, quantity_within_refundable, order_cap, approval_threshold, customer_cap]
)
def test_line_rules_defer_to_rule_three_when_the_item_is_missing(
    rule: RuleFn, check_factory: CheckFactory, config: PolicyConfig
) -> None:
    assert rule(check_factory(build_order(), item_id=ItemId("nope")), config) is None


def test_rules_are_listed_in_design_table_order() -> None:
    assert [rule.__name__ for rule in RULES] == [
        "order_in_scope",
        "order_status_eligible",
        "item_on_order",
        "something_left_to_refund",
        "quantity_within_refundable",
        "order_cap",
        "approval_threshold",
        "customer_cap",
    ]


def test_confirmation_carries_the_computed_amount(check_factory: CheckFactory) -> None:
    decision = confirmation_required(check_factory(build_order(price="12.50")))

    assert decision == Decision(DecisionKind.NEEDS_CONFIRMATION, ReasonCode.CONFIRMATION_REQUIRED, eur("12.50"))


def test_confirmation_without_an_order_denies(check_factory: CheckFactory) -> None:
    assert confirmation_required(check_factory(None)).kind is DecisionKind.DENY


def test_dispute_fires_when_a_claim_exceeds_the_computed_amount(check_factory: CheckFactory) -> None:
    check = check_factory(build_order(), claimed=(eur("5.00"), eur("25.00")))

    assert amount_dispute(check, eur("10.00")) == Decision(
        DecisionKind.ESCALATE, ReasonCode.AMOUNT_DISPUTE, eur("10.00")
    )


def test_dispute_is_quiet_when_claims_do_not_exceed_the_computed_amount(check_factory: CheckFactory) -> None:
    check = check_factory(build_order(), claimed=(eur("10.00"), eur("3.00")))

    assert amount_dispute(check, eur("10.00")) is None


def test_dispute_is_quiet_without_claims(check_factory: CheckFactory) -> None:
    assert amount_dispute(check_factory(build_order()), eur("10.00")) is None


def test_threshold_counts_earlier_refunds_on_the_same_order(check_factory: CheckFactory, config: PolicyConfig) -> None:
    earlier = (build_record(amount="40.00", quantity=2),)
    check = check_factory(build_order(price="20.00", quantity=4), quantity=1, order_refunds=earlier)

    assert approval_threshold(check, config) == Decision(
        DecisionKind.ESCALATE, ReasonCode.ABOVE_APPROVAL_THRESHOLD, eur("20.00")
    )


def test_threshold_ignores_refunds_that_were_not_issued(check_factory: CheckFactory, config: PolicyConfig) -> None:
    rejected = (build_record(amount="40.00", quantity=2, state=RefundState.REJECTED),)
    check = check_factory(build_order(price="20.00", quantity=4), quantity=1, order_refunds=rejected)

    assert approval_threshold(check, config) is None

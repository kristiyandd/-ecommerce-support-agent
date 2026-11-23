from collections.abc import Callable

from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import ItemId
from support_agent.domain.orders import OrderStatus
from support_agent.policy.config import PolicyConfig
from support_agent.policy.engine import PolicyEngine
from support_agent.policy.rules import RefundCheck

from .conftest import build_config, build_order, build_record, eur

CheckFactory = Callable[..., RefundCheck]


def test_missing_order_is_denied_without_amount(check_factory: CheckFactory, config: PolicyConfig) -> None:
    assessment = PolicyEngine(config).assess_refund(check_factory(None))

    assert assessment.decision == Decision(DecisionKind.DENY, ReasonCode.ORDER_NOT_FOUND, None)


def test_first_failing_rule_wins_over_later_failures(check_factory: CheckFactory, config: PolicyConfig) -> None:
    order = build_order(status=OrderStatus.IN_TRANSIT, price="500.00")
    check = check_factory(order, item_id=ItemId("nope"), quantity=9)

    assert PolicyEngine(config).assess_refund(check).decision.reason is ReasonCode.ORDER_NOT_ELIGIBLE


def test_already_refunded_beats_quantity_and_amount_rules(check_factory: CheckFactory, config: PolicyConfig) -> None:
    order = build_order(price="500.00", quantity=1)
    check = check_factory(order, quantity=3, order_refunds=(build_record("500.00"),))

    assert PolicyEngine(config).assess_refund(check).decision.reason is ReasonCode.ALREADY_REFUNDED


def test_threshold_beats_customer_cap(check_factory: CheckFactory) -> None:
    config = build_config(threshold="50.00", cap="10.00")
    check = check_factory(build_order(price="60.00", quantity=1))

    assert PolicyEngine(config).assess_refund(check).decision.reason is ReasonCode.ABOVE_APPROVAL_THRESHOLD


def test_partial_quantity_refunds_exactly_one_unit_price(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(price="14.90", quantity=2), quantity=1)

    decision = PolicyEngine(config).assess_refund(check).decision

    assert decision == Decision(DecisionKind.NEEDS_CONFIRMATION, ReasonCode.CONFIRMATION_REQUIRED, eur("14.90"))


def test_cumulative_cap_applies_after_an_earlier_refund(check_factory: CheckFactory, config: PolicyConfig) -> None:
    earlier = (build_record("95.00", order_id=build_order().order_id, item_id=ItemId("other")),)
    check = check_factory(build_order(price="10.00", quantity=1), customer_refunds=earlier)

    decision = PolicyEngine(config).assess_refund(check).decision

    assert decision == Decision(DecisionKind.ESCALATE, ReasonCode.CUSTOMER_LIMIT_EXCEEDED, eur("10.00"))


def test_dispute_accompanies_a_confirmation_when_claim_is_higher(
    check_factory: CheckFactory, config: PolicyConfig
) -> None:
    check = check_factory(build_order(price="10.00"), claimed=(eur("40.00"),))

    assessment = PolicyEngine(config).assess_refund(check)

    assert assessment.decision.kind is DecisionKind.NEEDS_CONFIRMATION
    assert assessment.dispute == Decision(DecisionKind.ESCALATE, ReasonCode.AMOUNT_DISPUTE, eur("10.00"))


def test_dispute_accompanies_an_escalation_with_computed_amount(
    check_factory: CheckFactory, config: PolicyConfig
) -> None:
    check = check_factory(build_order(price="60.00", quantity=1), claimed=(eur("90.00"),))

    assessment = PolicyEngine(config).assess_refund(check)

    assert assessment.decision.reason is ReasonCode.ABOVE_APPROVAL_THRESHOLD
    assert assessment.dispute == Decision(DecisionKind.ESCALATE, ReasonCode.AMOUNT_DISPUTE, eur("60.00"))


def test_no_dispute_when_claim_equals_computed_amount(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(price="10.00"), claimed=(eur("10.00"),))

    assert PolicyEngine(config).assess_refund(check).dispute is None


def test_no_dispute_when_the_decision_is_a_deny(check_factory: CheckFactory, config: PolicyConfig) -> None:
    check = check_factory(build_order(status=OrderStatus.IN_TRANSIT), claimed=(eur("999.00"),))

    assessment = PolicyEngine(config).assess_refund(check)

    assert assessment.decision.kind is DecisionKind.DENY
    assert assessment.dispute is None

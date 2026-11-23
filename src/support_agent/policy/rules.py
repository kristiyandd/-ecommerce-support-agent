"""Refund policy rules in table order (design section 4). Each returns None when it passes."""

from collections.abc import Callable
from dataclasses import dataclass

from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import ItemId
from support_agent.domain.money import Money
from support_agent.domain.orders import Order, OrderLine
from support_agent.domain.refunds import RefundRecord
from support_agent.policy.config import PolicyConfig
from support_agent.policy.refund_amounts import refund_amount, refundable_quantity, refunded_total

MIN_QUANTITY = 1


@dataclass(frozen=True)
class RefundCheck:
    order: Order | None
    item_id: ItemId
    quantity: int
    claimed_amounts: tuple[Money, ...]
    order_refunds: tuple[RefundRecord, ...]
    customer_refunds: tuple[RefundRecord, ...]


Rule = Callable[[RefundCheck, PolicyConfig], Decision | None]


def _deny(reason: ReasonCode) -> Decision:
    return Decision(DecisionKind.DENY, reason)


def resolve_line(check: RefundCheck) -> tuple[Order, OrderLine] | None:
    if check.order is None:
        return None
    line = check.order.line(check.item_id)
    return None if line is None else (check.order, line)


def order_in_scope(check: RefundCheck, _config: PolicyConfig) -> Decision | None:
    return _deny(ReasonCode.ORDER_NOT_FOUND) if check.order is None else None


def order_status_eligible(check: RefundCheck, config: PolicyConfig) -> Decision | None:
    if check.order is not None and check.order.status not in config.refundable_statuses:
        return _deny(ReasonCode.ORDER_NOT_ELIGIBLE)
    return None


def item_on_order(check: RefundCheck, _config: PolicyConfig) -> Decision | None:
    if check.order is not None and check.order.line(check.item_id) is None:
        return _deny(ReasonCode.ITEM_NOT_ON_ORDER)
    return None


def something_left_to_refund(check: RefundCheck, _config: PolicyConfig) -> Decision | None:
    resolved = resolve_line(check)
    if resolved is not None and refundable_quantity(resolved[1], check.order_refunds) == 0:
        return _deny(ReasonCode.ALREADY_REFUNDED)
    return None


def quantity_within_refundable(check: RefundCheck, _config: PolicyConfig) -> Decision | None:
    resolved = resolve_line(check)
    if resolved is None:
        return None
    if check.quantity < MIN_QUANTITY or check.quantity > refundable_quantity(resolved[1], check.order_refunds):
        return _deny(ReasonCode.QUANTITY_EXCEEDS_REFUNDABLE)
    return None


def order_cap(check: RefundCheck, _config: PolicyConfig) -> Decision | None:
    resolved = resolve_line(check)
    if resolved is None:
        return None
    order, line = resolved
    already = refunded_total(check.order_refunds, order.total.currency)
    if already + refund_amount(line, check.quantity) > order.total:
        return _deny(ReasonCode.EXCEEDS_AMOUNT_PAID)
    return None


def approval_threshold(check: RefundCheck, config: PolicyConfig) -> Decision | None:
    """Cumulative per order, so splitting one refund into smaller requests cannot avoid human approval."""
    resolved = resolve_line(check)
    if resolved is None:
        return None
    amount = refund_amount(resolved[1], check.quantity)
    already = refunded_total(check.order_refunds, amount.currency)
    if already + amount > config.approval_threshold:
        return Decision(DecisionKind.ESCALATE, ReasonCode.ABOVE_APPROVAL_THRESHOLD, amount)
    return None


def customer_cap(check: RefundCheck, config: PolicyConfig) -> Decision | None:
    resolved = resolve_line(check)
    if resolved is None:
        return None
    amount = refund_amount(resolved[1], check.quantity)
    already = refunded_total(check.customer_refunds, amount.currency)
    if already + amount > config.customer_auto_refund_cap:
        return Decision(DecisionKind.ESCALATE, ReasonCode.CUSTOMER_LIMIT_EXCEEDED, amount)
    return None


RULES: tuple[Rule, ...] = (
    order_in_scope,
    order_status_eligible,
    item_on_order,
    something_left_to_refund,
    quantity_within_refundable,
    order_cap,
    approval_threshold,
    customer_cap,
)


def confirmation_required(check: RefundCheck) -> Decision:
    resolved = resolve_line(check)
    if resolved is None:
        return _deny(ReasonCode.ORDER_NOT_FOUND)
    amount = refund_amount(resolved[1], check.quantity)
    return Decision(DecisionKind.NEEDS_CONFIRMATION, ReasonCode.CONFIRMATION_REQUIRED, amount)


def disputed_claim(check: RefundCheck, computed: Money) -> Money | None:
    """The highest claim above the record amount; quoting the order total is context, not a claim."""
    order_total = check.order.total if check.order is not None else None
    disputing = [claimed for claimed in check.claimed_amounts if claimed > computed and claimed != order_total]
    return max(disputing, key=lambda money: money.amount) if disputing else None


def amount_dispute(check: RefundCheck, computed: Money) -> Decision | None:
    if disputed_claim(check, computed) is None:
        return None
    return Decision(DecisionKind.ESCALATE, ReasonCode.AMOUNT_DISPUTE, computed)

from collections.abc import Callable
from typing import Any

import pytest

from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId, RefundId, TraceId
from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import Order, OrderLine, OrderStatus
from support_agent.domain.refunds import RefundReason, RefundRecord, RefundState
from support_agent.policy.config import PolicyConfig
from support_agent.policy.rules import RefundCheck

CUSTOMER = CustomerId("C-1")
ORDER = OrderId("O-1")
ITEM = ItemId("I-1")


def eur(value: str) -> Money:
    return Money.parse(value, Currency.EUR)


def build_config(threshold: str = "50.00", cap: str = "100.00") -> PolicyConfig:
    return PolicyConfig(
        version="test",
        currency=Currency.EUR,
        approval_threshold=eur(threshold),
        customer_auto_refund_cap=eur(cap),
        refundable_statuses=frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED}),
    )


def build_order(
    price: str = "10.00",
    quantity: int = 2,
    status: OrderStatus = OrderStatus.DELIVERED,
    total: str | None = None,
) -> Order:
    line = OrderLine(item_id=ITEM, name="Mug", quantity=quantity, unit_price=eur(price))
    order_total = eur(total) if total is not None else line.unit_price.times(quantity)
    return Order(order_id=ORDER, customer_id=CUSTOMER, status=status, total=order_total, lines=(line,), shipping=None)


def build_record(
    amount: str = "10.00",
    quantity: int = 1,
    state: RefundState = RefundState.ISSUED,
    order_id: OrderId = ORDER,
    item_id: ItemId = ITEM,
) -> RefundRecord:
    return RefundRecord(
        refund_id=RefundId("RF-x"),
        idempotency_key=IdempotencyKey(f"k-{amount}-{quantity}-{order_id}-{state}"),
        customer_id=CUSTOMER,
        order_id=order_id,
        item_id=item_id,
        quantity=quantity,
        amount=eur(amount),
        reason=RefundReason.DAMAGED,
        state=state,
        trace_id=TraceId("t-1"),
    )


CHECK_DEFAULTS: dict[str, Any] = {"item_id": ITEM, "claimed": (), "order_refunds": (), "customer_refunds": ()}


def build_check(order: Order | None, quantity: int = 1, **fields: Any) -> RefundCheck:
    if unknown := fields.keys() - CHECK_DEFAULTS.keys():
        raise TypeError(sorted(unknown))
    values = CHECK_DEFAULTS | fields
    return RefundCheck(
        order=order,
        item_id=values["item_id"],
        quantity=quantity,
        claimed_amounts=values["claimed"],
        order_refunds=values["order_refunds"],
        customer_refunds=values["customer_refunds"],
    )


@pytest.fixture
def config() -> PolicyConfig:
    return build_config()


@pytest.fixture
def check_factory() -> Callable[..., RefundCheck]:
    return build_check

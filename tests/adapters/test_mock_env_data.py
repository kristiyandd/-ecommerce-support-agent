from decimal import Decimal

import pytest

from mock_env import MockCommerceEnv
from support_agent.adapters.mock_env_data import MockEnvDataFactory
from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId, RefundId, TraceId
from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import OrderStatus
from support_agent.domain.refunds import RefundReason, RefundRecord, RefundState


def _first_order_of_other_customer(env: MockCommerceEnv, customer: str) -> str:
    return next(str(raw["order_id"]) for raw in env.orders() if raw["customer_id"] != customer)


def _refund(customer: str, key: str = "K-1") -> RefundRecord:
    return RefundRecord(
        RefundId("R-1"),
        IdempotencyKey(key),
        CustomerId(customer),
        OrderId("O-1"),
        ItemId("I-1"),
        1,
        Money(Decimal("1.00"), Currency.EUR),
        RefundReason.OTHER,
        RefundState.ISSUED,
        TraceId("T-1"),
    )


def test_orders_are_scoped_to_the_customer(env: MockCommerceEnv) -> None:
    orders = MockEnvDataFactory(env).orders_for(CustomerId("CUST-001")).list_orders()

    assert orders
    assert {order.customer_id for order in orders} == {"CUST-001"}


def test_foreign_order_looks_exactly_like_a_missing_order(env: MockCommerceEnv) -> None:
    scope = MockEnvDataFactory(env).orders_for(CustomerId("CUST-001"))
    foreign = _first_order_of_other_customer(env, "CUST-001")

    assert scope.find_order(OrderId(foreign)) is None
    assert scope.find_order(OrderId("ORD-DOES-NOT-EXIST")) is None


def test_seed_prices_become_exact_money(env: MockCommerceEnv) -> None:
    order = MockEnvDataFactory(env).orders_for(CustomerId("CUST-001")).list_orders()[0]

    assert all(isinstance(line.unit_price.amount, Decimal) for line in order.lines)
    assert order.status in set(OrderStatus)


def test_refund_round_trips_through_runtime_storage(env: MockCommerceEnv) -> None:
    refunds = MockEnvDataFactory(env).refunds_for(CustomerId("C-1"))

    refunds.add(_refund("C-1"))

    assert refunds.all() == (_refund("C-1"),)
    assert refunds.for_order(OrderId("O-1")) == (_refund("C-1"),)
    assert refunds.find_by_key(IdempotencyKey("K-1")) == _refund("C-1")


def test_refunds_of_other_customers_are_invisible(env: MockCommerceEnv) -> None:
    factory = MockEnvDataFactory(env)
    factory.refunds_for(CustomerId("C-2")).add(_refund("C-2"))

    assert factory.refunds_for(CustomerId("C-1")).all() == ()


def test_adding_a_refund_for_another_customer_is_a_programming_error(env: MockCommerceEnv) -> None:
    with pytest.raises(ValueError, match="customer scope"):
        MockEnvDataFactory(env).refunds_for(CustomerId("C-1")).add(_refund("C-2"))

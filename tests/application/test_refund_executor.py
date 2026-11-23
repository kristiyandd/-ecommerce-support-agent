import itertools
from collections.abc import Callable
from dataclasses import replace

import pytest

from support_agent.application.context import TurnContext
from support_agent.application.refund_executor import RefundExecutor
from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId, RefundId, TraceId
from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import Order, OrderLine, OrderStatus
from support_agent.domain.refunds import RefundReason, RefundRecord, RefundState
from support_agent.domain.turn import ActionOutcome, ProposedRefund
from support_agent.policy.config import PolicyConfig
from support_agent.policy.engine import PolicyEngine

CUSTOMER = CustomerId("C-1")
ORDER = OrderId("O-1")
ITEM = ItemId("I-1")
TRACE = TraceId("t-1")


def eur(value: str) -> Money:
    return Money.parse(value, Currency.EUR)


class FakeOrders:
    def __init__(self, orders: tuple[Order, ...]) -> None:
        self._orders = orders

    def list_orders(self) -> tuple[Order, ...]:
        return self._orders

    def find_order(self, order_id: OrderId) -> Order | None:
        return next((order for order in self._orders if order.order_id == order_id), None)


class FakeRefunds:
    def __init__(self) -> None:
        self.records: list[RefundRecord] = []

    def for_order(self, order_id: OrderId) -> tuple[RefundRecord, ...]:
        return tuple(record for record in self.records if record.order_id == order_id)

    def all(self) -> tuple[RefundRecord, ...]:
        return tuple(self.records)

    def find_by_key(self, key: IdempotencyKey) -> RefundRecord | None:
        return next((record for record in self.records if record.idempotency_key == key), None)

    def add(self, record: RefundRecord) -> None:
        self.records.append(record)


def build_config(threshold: str = "50.00") -> PolicyConfig:
    return PolicyConfig(
        version="test",
        currency=Currency.EUR,
        approval_threshold=eur(threshold),
        customer_auto_refund_cap=eur("100.00"),
        refundable_statuses=frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED}),
    )


def build_order(status: OrderStatus = OrderStatus.DELIVERED) -> Order:
    line = OrderLine(item_id=ITEM, name="Mug", quantity=2, unit_price=eur("10.00"))
    return Order(order_id=ORDER, customer_id=CUSTOMER, status=status, total=eur("20.00"), lines=(line,), shipping=None)


def build_proposal(amount: str = "10.00", key: str = "key-1") -> ProposedRefund:
    return ProposedRefund(
        order_id=ORDER,
        item_id=ITEM,
        item_name="Mug",
        quantity=1,
        amount=eur(amount),
        reason=RefundReason.DAMAGED,
        idempotency_key=IdempotencyKey(key),
    )


@pytest.fixture
def new_id() -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"n{next(counter)}"


@pytest.fixture
def executor(new_id: Callable[[], str]) -> RefundExecutor:
    return RefundExecutor(PolicyEngine(build_config()), new_id)


def run(
    executor: RefundExecutor, proposal: ProposedRefund, orders: FakeOrders, refunds: FakeRefunds
) -> ActionOutcome | Decision:
    return executor.execute(proposal, TurnContext(CUSTOMER, orders, refunds, ()), TRACE)


def test_confirmed_proposal_is_issued_as_a_record(executor: RefundExecutor) -> None:
    refunds = FakeRefunds()

    outcome = run(executor, build_proposal(), FakeOrders((build_order(),)), refunds)

    assert outcome == ActionOutcome(
        refund_id=RefundId("RF-n1"),
        order_id=ORDER,
        item_id=ITEM,
        quantity=1,
        amount=eur("10.00"),
        state=RefundState.ISSUED,
    )
    assert len(refunds.records) == 1
    assert refunds.records[0].trace_id == TRACE
    assert refunds.records[0].customer_id == CUSTOMER
    assert refunds.records[0].state is RefundState.ISSUED


def test_replay_returns_the_same_refund_without_adding_another(executor: RefundExecutor) -> None:
    refunds = FakeRefunds()
    orders = FakeOrders((build_order(),))
    first = run(executor, build_proposal(), orders, refunds)

    second = run(executor, build_proposal(), orders, refunds)

    assert isinstance(first, ActionOutcome)
    assert second == replace(first, replayed=True)
    assert len(refunds.records) == 1


def test_changed_amount_is_stale_and_adds_nothing(executor: RefundExecutor) -> None:
    refunds = FakeRefunds()

    outcome = run(executor, build_proposal(amount="12.00"), FakeOrders((build_order(),)), refunds)

    assert outcome == Decision(DecisionKind.DENY, ReasonCode.CONFIRMATION_STALE)
    assert refunds.records == []


def test_policy_that_now_denies_adds_nothing(executor: RefundExecutor) -> None:
    refunds = FakeRefunds()

    outcome = run(executor, build_proposal(), FakeOrders((build_order(OrderStatus.IN_TRANSIT),)), refunds)

    assert outcome == Decision(DecisionKind.DENY, ReasonCode.CONFIRMATION_STALE)
    assert refunds.records == []


def test_order_that_disappeared_adds_nothing(executor: RefundExecutor) -> None:
    refunds = FakeRefunds()

    outcome = run(executor, build_proposal(), FakeOrders(()), refunds)

    assert outcome == Decision(DecisionKind.DENY, ReasonCode.CONFIRMATION_STALE)
    assert refunds.records == []


def test_policy_that_now_escalates_is_stale(new_id: Callable[[], str]) -> None:
    strict = RefundExecutor(PolicyEngine(build_config(threshold="5.00")), new_id)
    refunds = FakeRefunds()

    outcome = run(strict, build_proposal(), FakeOrders((build_order(),)), refunds)

    assert outcome == Decision(DecisionKind.DENY, ReasonCode.CONFIRMATION_STALE)
    assert refunds.records == []


def test_second_unit_with_a_new_key_is_issued_after_the_first(executor: RefundExecutor) -> None:
    refunds = FakeRefunds()
    orders = FakeOrders((build_order(),))
    run(executor, build_proposal(key="key-1"), orders, refunds)

    outcome = run(executor, build_proposal(key="key-2"), orders, refunds)

    assert isinstance(outcome, ActionOutcome)
    assert len(refunds.records) == 2


def test_third_unit_is_stale_once_all_units_are_refunded(executor: RefundExecutor) -> None:
    refunds = FakeRefunds()
    orders = FakeOrders((build_order(),))
    run(executor, build_proposal(key="key-1"), orders, refunds)
    run(executor, build_proposal(key="key-2"), orders, refunds)

    outcome = run(executor, build_proposal(key="key-3"), orders, refunds)

    assert outcome == Decision(DecisionKind.DENY, ReasonCode.CONFIRMATION_STALE)
    assert len(refunds.records) == 2

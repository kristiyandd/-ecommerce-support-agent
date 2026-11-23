"""Customer-scoped repositories over the mock commerce environment."""

from typing import Any

from mock_env import MockCommerceEnv
from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId, RefundId, TraceId
from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import Order, OrderLine, OrderStatus, Shipping
from support_agent.domain.refunds import RefundReason, RefundRecord, RefundState

REFUNDS_COLLECTION = "refunds"
KNOWN_STATUSES = frozenset(status.value for status in OrderStatus)


def _line_from_seed(raw: dict[str, Any], currency: Currency) -> OrderLine:
    return OrderLine(
        ItemId(raw["item_id"]), raw["name"], int(raw["quantity"]), Money.parse(raw["unit_price"], currency)
    )


def _order_from_seed(raw: dict[str, Any]) -> Order:
    currency = Currency(raw["currency"])
    shipping = raw.get("shipping")
    status = raw["status"] if raw["status"] in KNOWN_STATUSES else OrderStatus.UNKNOWN
    return Order(
        order_id=OrderId(raw["order_id"]),
        customer_id=CustomerId(raw["customer_id"]),
        status=OrderStatus(status),
        total=Money.parse(raw["total"], currency),
        lines=tuple(_line_from_seed(item, currency) for item in raw["items"]),
        shipping=Shipping(shipping["carrier"], shipping["tracking_number"]) if shipping else None,
    )


def _refund_to_dict(refund: RefundRecord) -> dict[str, Any]:
    return {
        "refund_id": refund.refund_id,
        "idempotency_key": refund.idempotency_key,
        "customer_id": refund.customer_id,
        "order_id": refund.order_id,
        "item_id": refund.item_id,
        "quantity": refund.quantity,
        "amount": str(refund.amount.amount),
        "currency": refund.amount.currency.value,
        "reason": refund.reason.value,
        "state": refund.state.value,
        "trace_id": refund.trace_id,
    }


def _refund_from_dict(raw: dict[str, Any]) -> RefundRecord:
    return RefundRecord(
        refund_id=RefundId(raw["refund_id"]),
        idempotency_key=IdempotencyKey(raw["idempotency_key"]),
        customer_id=CustomerId(raw["customer_id"]),
        order_id=OrderId(raw["order_id"]),
        item_id=ItemId(raw["item_id"]),
        quantity=int(raw["quantity"]),
        amount=Money.parse(raw["amount"], Currency(raw["currency"])),
        reason=RefundReason(raw["reason"]),
        state=RefundState(raw["state"]),
        trace_id=TraceId(raw["trace_id"]),
    )


class ScopeViolationError(ValueError):
    def __init__(self) -> None:
        super().__init__("refund record does not belong to this customer scope")


class MockEnvCustomerOrders:
    def __init__(self, env: MockCommerceEnv, customer_id: CustomerId) -> None:
        self._env = env
        self._customer_id = customer_id

    def list_orders(self) -> tuple[Order, ...]:
        return tuple(_order_from_seed(raw) for raw in self._env.orders() if raw["customer_id"] == self._customer_id)

    def find_order(self, order_id: OrderId) -> Order | None:
        return next((order for order in self.list_orders() if order.order_id == order_id), None)


class MockEnvCustomerRefunds:
    def __init__(self, env: MockCommerceEnv, customer_id: CustomerId) -> None:
        self._env = env
        self._customer_id = customer_id

    def all(self) -> tuple[RefundRecord, ...]:
        records = self._env.records(REFUNDS_COLLECTION)
        return tuple(_refund_from_dict(raw) for raw in records if raw["customer_id"] == self._customer_id)

    def for_order(self, order_id: OrderId) -> tuple[RefundRecord, ...]:
        return tuple(record for record in self.all() if record.order_id == order_id)

    def find_by_key(self, key: IdempotencyKey) -> RefundRecord | None:
        return next((record for record in self.all() if record.idempotency_key == key), None)

    def add(self, record: RefundRecord) -> None:
        if record.customer_id != self._customer_id:
            raise ScopeViolationError
        self._env.append_record(REFUNDS_COLLECTION, _refund_to_dict(record))


class MockEnvDataFactory:
    def __init__(self, env: MockCommerceEnv) -> None:
        self._env = env

    def orders_for(self, customer_id: CustomerId) -> MockEnvCustomerOrders:
        return MockEnvCustomerOrders(self._env, customer_id)

    def refunds_for(self, customer_id: CustomerId) -> MockEnvCustomerRefunds:
        return MockEnvCustomerRefunds(self._env, customer_id)

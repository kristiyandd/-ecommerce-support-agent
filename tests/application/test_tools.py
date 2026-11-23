import json
from decimal import Decimal

import pytest

from support_agent.adapters.policy_file import policy_config_from_mapping
from support_agent.application.model_protocol import ToolCall
from support_agent.application.tools import ToolFault, ToolOutcome, ToolRegistry, TurnContext
from support_agent.domain.decisions import DecisionKind, ReasonCode
from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId, RefundId, TraceId
from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import Order, OrderLine, OrderStatus, Shipping
from support_agent.domain.refunds import RefundReason, RefundRecord, RefundState
from support_agent.policy.engine import PolicyEngine
from support_agent.policy.refund_amounts import idempotency_key

CUSTOMER = CustomerId("C-1")
EUR = Currency.EUR
CONFIG = {
    "version": "test",
    "currency": "EUR",
    "approval_threshold": "50.00",
    "customer_auto_refund_cap": "100.00",
    "refundable_statuses": ["delivered", "returned"],
}


def money(value: str) -> Money:
    return Money.parse(value, EUR)


LAMP = OrderLine(ItemId("I-1"), "Desk Lamp", 3, money("12.50"))
SOFA = OrderLine(ItemId("I-2"), "Sofa", 1, money("80.00"))
DELIVERED = Order(OrderId("X-1"), CUSTOMER, OrderStatus.DELIVERED, money("117.50"), (LAMP, SOFA), None)
SHIPPED = Order(OrderId("X-2"), CUSTOMER, OrderStatus.IN_TRANSIT, money("12.50"), (LAMP,), Shipping("UPS", "TRK-9"))


class FakeOrders:
    def __init__(self, *orders: Order) -> None:
        self._orders = {order.order_id: order for order in orders}

    def list_orders(self) -> tuple[Order, ...]:
        return tuple(self._orders.values())

    def find_order(self, order_id: OrderId) -> Order | None:
        return self._orders.get(order_id)


class FakeRefunds:
    def __init__(self, *records: RefundRecord) -> None:
        self.records = list(records)

    def for_order(self, order_id: OrderId) -> tuple[RefundRecord, ...]:
        return tuple(r for r in self.records if r.order_id == order_id)

    def all(self) -> tuple[RefundRecord, ...]:
        return tuple(self.records)

    def find_by_key(self, key: IdempotencyKey) -> RefundRecord | None:
        return next((r for r in self.records if r.idempotency_key == key), None)

    def add(self, record: RefundRecord) -> None:
        self.records.append(record)


def issued(quantity: int) -> RefundRecord:
    return RefundRecord(
        RefundId("R-1"),
        IdempotencyKey("k"),
        CUSTOMER,
        DELIVERED.order_id,
        LAMP.item_id,
        quantity,
        LAMP.unit_price.times(quantity),
        RefundReason.OTHER,
        RefundState.ISSUED,
        TraceId("t"),
    )


def context(*claimed: str, refunds: FakeRefunds | None = None) -> TurnContext:
    return TurnContext(
        CUSTOMER,
        FakeOrders(DELIVERED, SHIPPED),
        refunds or FakeRefunds(),
        tuple(money(value) for value in claimed),
    )


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry(PolicyEngine(policy_config_from_mapping(CONFIG)))


def call(name: str, **arguments: object) -> ToolCall:
    return ToolCall("call-1", name, json.dumps(arguments))


def outcome(registry: ToolRegistry, ctx: TurnContext, name: str, **arguments: object) -> ToolOutcome:
    result = registry.run(call(name, **arguments), ctx)
    assert isinstance(result, ToolOutcome)
    return result


def refund_args(
    item: ItemId = LAMP.item_id, quantity: int = 1, order: OrderId = DELIVERED.order_id
) -> dict[str, object]:
    return {"order_id": order, "item_id": item, "quantity": quantity, "reason": "damaged"}


def test_schemas_list_all_tools(registry: ToolRegistry) -> None:
    schemas = {schema.name: schema for schema in registry.schemas()}
    assert set(schemas) == {"list_my_orders", "get_order", "request_refund", "escalate_to_human"}
    assert all(schema.description for schema in schemas.values())
    assert "amount" not in str(schemas["request_refund"].parameters["properties"])
    assert schemas["request_refund"].parameters["required"] == ["order_id", "item_id", "quantity", "reason"]


def test_list_my_orders(registry: ToolRegistry) -> None:
    result = outcome(registry, context(), "list_my_orders").result
    assert result == {
        "orders": [{"order_id": "X-1", "status": "delivered"}, {"order_id": "X-2", "status": "in_transit"}]
    }


def test_get_order_found_with_refunded_quantity(registry: ToolRegistry) -> None:
    result = outcome(registry, context(refunds=FakeRefunds(issued(2))), "get_order", order_id="X-1").result
    assert result["found"] is True
    assert result["total"] == "117.50"
    assert result["currency"] == "EUR"
    assert result["shipping"] is None
    assert result["lines"] == [
        {"item_id": "I-1", "name": "Desk Lamp", "quantity": 3, "unit_price": "12.50", "refunded_quantity": 2},
        {"item_id": "I-2", "name": "Sofa", "quantity": 1, "unit_price": "80.00", "refunded_quantity": 0},
    ]


def test_get_order_shipping(registry: ToolRegistry) -> None:
    result = outcome(registry, context(), "get_order", order_id="X-2").result
    assert result["shipping"] == {"carrier": "UPS", "tracking_number": "TRK-9"}


def test_get_order_has_no_customer_fields(registry: ToolRegistry) -> None:
    text = json.dumps(outcome(registry, context(), "get_order", order_id="X-1").result)
    assert "C-1" not in text
    assert "customer" not in text


def test_not_found_equals_foreign(registry: ToolRegistry) -> None:
    ctx = context()
    missing = outcome(registry, ctx, "get_order", order_id="X-404")
    assert missing.result == {"found": False}
    refund = outcome(registry, ctx, "request_refund", **refund_args(order=OrderId("X-404")))
    assert refund.decision is not None
    assert refund.decision.reason is ReasonCode.ORDER_NOT_FOUND
    assert refund.result == {"decision": "deny", "reason_code": "order_not_found"}
    assert refund.proposal is None


def test_request_refund_proposes_with_idempotency_key(registry: ToolRegistry) -> None:
    result = outcome(registry, context(refunds=FakeRefunds(issued(1))), "request_refund", **refund_args())
    assert result.result == {
        "decision": "needs_confirmation",
        "reason_code": "confirmation_required",
        "item_name": "Desk Lamp",
        "quantity": 1,
    }
    assert result.proposal is not None
    assert result.proposal.amount == money("12.50")
    assert result.proposal.reason is RefundReason.DAMAGED
    assert result.proposal.idempotency_key == idempotency_key(CUSTOMER, DELIVERED.order_id, LAMP.item_id, 1, 1)
    assert tuple(item.reason for item in result.escalations) == ()


def test_proposal_key_differs_after_earlier_refund(registry: ToolRegistry) -> None:
    fresh = outcome(registry, context(), "request_refund", **refund_args()).proposal
    later = outcome(registry, context(refunds=FakeRefunds(issued(1))), "request_refund", **refund_args()).proposal
    assert fresh is not None
    assert later is not None
    assert fresh.idempotency_key != later.idempotency_key


def test_request_refund_denied_for_ineligible_status(registry: ToolRegistry) -> None:
    result = outcome(registry, context(), "request_refund", **refund_args(order=SHIPPED.order_id))
    assert result.decision is not None
    assert result.decision.kind is DecisionKind.DENY
    assert result.proposal is None
    assert tuple(item.reason for item in result.escalations) == ()


def test_request_refund_above_threshold_escalates(registry: ToolRegistry) -> None:
    result = outcome(registry, context(), "request_refund", **refund_args(item=SOFA.item_id))
    assert result.decision is not None
    assert result.decision.kind is DecisionKind.ESCALATE
    assert result.proposal is None
    assert tuple(item.reason for item in result.escalations) == (ReasonCode.ABOVE_APPROVAL_THRESHOLD,)
    assert result.decision.amount == money("80.00")


def test_dispute_flag_without_claimed_amount(registry: ToolRegistry) -> None:
    result = outcome(registry, context("99.00"), "request_refund", **refund_args())
    assert result.result["amount_dispute"] is True
    assert "99" not in json.dumps(result.result)
    assert ReasonCode.AMOUNT_DISPUTE in tuple(item.reason for item in result.escalations)
    assert result.decision is not None
    assert result.decision.amount is not None
    assert result.decision.amount.amount == Decimal("12.50")


def test_no_dispute_when_claim_not_higher(registry: ToolRegistry) -> None:
    result = outcome(registry, context("12.50"), "request_refund", **refund_args())
    assert "amount_dispute" not in result.result
    assert tuple(item.reason for item in result.escalations) == ()


def test_escalate_to_human(registry: ToolRegistry) -> None:
    result = outcome(registry, context(), "escalate_to_human")
    assert result.result == {"escalated": True}
    assert result.decision is not None
    assert result.decision.reason is ReasonCode.CUSTOMER_REQUESTED_HUMAN
    assert tuple(item.reason for item in result.escalations) == (ReasonCode.CUSTOMER_REQUESTED_HUMAN,)


def test_unknown_tool(registry: ToolRegistry) -> None:
    fault = registry.run(call("transfer_money"), context())
    assert isinstance(fault, ToolFault)
    assert fault.reason is ReasonCode.UNKNOWN_TOOL


@pytest.mark.parametrize(
    "raw",
    ["{", '{"order_id": "X-1", "item_id": "I-1", "quantity": 1, "reason": "other", "amount": "5.00"}'],
)
def test_invalid_arguments_fault(registry: ToolRegistry, raw: str) -> None:
    fault = registry.run(ToolCall("c", "request_refund", raw), context())
    assert isinstance(fault, ToolFault)
    assert fault.reason is ReasonCode.INVALID_ARGUMENTS


def test_quantity_below_minimum_faults(registry: ToolRegistry) -> None:
    fault = registry.run(call("request_refund", **refund_args(quantity=0)), context())
    assert isinstance(fault, ToolFault)
    assert fault.reason is ReasonCode.INVALID_ARGUMENTS

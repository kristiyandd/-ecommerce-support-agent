"""Tool commands and their registry; no tool can move money, request_refund only proposes."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import Field

from support_agent.application.context import TurnContext, refund_check
from support_agent.application.model_protocol import ToolCall, ToolSchema
from support_agent.application.tool_schema import ToolArguments, ToolFault, parse_arguments, schema_for
from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import ItemId, OrderId
from support_agent.domain.orders import Order, OrderLine
from support_agent.domain.refunds import RefundReason
from support_agent.domain.turn import EscalationItem, ProposedRefund
from support_agent.policy.engine import PolicyEngine, RefundAssessment
from support_agent.policy.refund_amounts import idempotency_key, refunded_quantity
from support_agent.policy.rules import MIN_QUANTITY, RefundCheck, disputed_claim


class ToolName(StrEnum):
    LIST_MY_ORDERS = "list_my_orders"
    GET_ORDER = "get_order"
    REQUEST_REFUND = "request_refund"
    ESCALATE_TO_HUMAN = "escalate_to_human"


LIST_DESCRIPTION = "List the customer's own orders and their status."
GET_ORDER_DESCRIPTION = "Look up one of the customer's orders by order ID."
REFUND_DESCRIPTION = "Ask for a refund of an item on an order. Only proposes; the customer must confirm."
ESCALATE_DESCRIPTION = "Hand the conversation to a human agent when the customer asks for a person."


class ResultKey(StrEnum):
    """Field names of tool results, the wire format the model reads."""

    ORDERS = "orders"
    FOUND = "found"
    ORDER_ID = "order_id"
    STATUS = "status"
    CURRENCY = "currency"
    TOTAL = "total"
    SHIPPING = "shipping"
    CARRIER = "carrier"
    TRACKING_NUMBER = "tracking_number"
    LINES = "lines"
    ITEM_ID = "item_id"
    NAME = "name"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    REFUNDED_QUANTITY = "refunded_quantity"
    DECISION = "decision"
    REASON_CODE = "reason_code"
    ITEM_NAME = "item_name"
    AMOUNT_DISPUTE = "amount_dispute"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class ToolOutcome:
    result: Mapping[str, object]
    decision: Decision | None = None
    proposal: ProposedRefund | None = None
    escalations: tuple[EscalationItem, ...] = ()
    shows_refund: bool = False
    dispute: Decision | None = None


class NoArguments(ToolArguments):
    pass


class GetOrderArguments(ToolArguments):
    order_id: str


class RequestRefundArguments(ToolArguments):
    order_id: str
    item_id: str
    quantity: int = Field(ge=MIN_QUANTITY)
    reason: RefundReason


@dataclass(frozen=True)
class Command[A: ToolArguments]:
    name: ToolName
    description: str
    arguments_type: type[A]
    handler: Callable[[A, TurnContext], ToolOutcome]


def _line_view(line: OrderLine, refunded: int) -> dict[str, object]:
    return {
        ResultKey.ITEM_ID: line.item_id,
        ResultKey.NAME: line.name,
        ResultKey.QUANTITY: line.quantity,
        ResultKey.UNIT_PRICE: str(line.unit_price.amount),
        ResultKey.REFUNDED_QUANTITY: refunded,
    }


def _shipping_view(order: Order) -> dict[str, str] | None:
    if order.shipping is None:
        return None
    return {ResultKey.CARRIER: order.shipping.carrier, ResultKey.TRACKING_NUMBER: order.shipping.tracking_number}


def _get_order(arguments: GetOrderArguments, context: TurnContext) -> ToolOutcome:
    order = context.orders.find_order(OrderId(arguments.order_id))
    if order is None:
        return ToolOutcome(result={ResultKey.FOUND: False})
    records = context.refunds.for_order(order.order_id)
    refunded = {line.item_id: refunded_quantity(line.item_id, records) for line in order.lines}
    view: dict[str, object] = {
        ResultKey.FOUND: True,
        ResultKey.ORDER_ID: order.order_id,
        ResultKey.STATUS: order.status.value,
        ResultKey.CURRENCY: order.total.currency.value,
        ResultKey.TOTAL: str(order.total.amount),
        ResultKey.SHIPPING: _shipping_view(order),
        ResultKey.LINES: [_line_view(line, refunded[line.item_id]) for line in order.lines],
    }
    return ToolOutcome(result=view, shows_refund=any(refunded.values()))


def _list_my_orders(_arguments: NoArguments, context: TurnContext) -> ToolOutcome:
    orders = [
        {ResultKey.ORDER_ID: order.order_id, ResultKey.STATUS: order.status.value}
        for order in context.orders.list_orders()
    ]
    return ToolOutcome(result={ResultKey.ORDERS: orders})


def _escalate_to_human(_arguments: NoArguments, _context: TurnContext) -> ToolOutcome:
    reason = ReasonCode.CUSTOMER_REQUESTED_HUMAN
    return ToolOutcome(
        result={ResultKey.ESCALATED: True},
        decision=Decision(DecisionKind.ESCALATE, reason),
        escalations=(EscalationItem(reason),),
    )


def _escalations(
    assessment: RefundAssessment, check: RefundCheck, line: OrderLine | None
) -> tuple[EscalationItem, ...]:
    if check.order is None or line is None:
        return ()
    items: list[EscalationItem] = []
    decision, dispute = assessment.decision, assessment.dispute
    if decision.kind is DecisionKind.ESCALATE:
        items.append(EscalationItem(decision.reason, check.order.order_id, line.item_id, decision.amount))
    if dispute is not None and dispute.amount is not None:
        claimed = disputed_claim(check, dispute.amount)
        items.append(EscalationItem(dispute.reason, check.order.order_id, line.item_id, dispute.amount, claimed))
    return tuple(items)


def _refund_result(assessment: RefundAssessment, line: OrderLine | None, quantity: int) -> dict[str, object]:
    decision = assessment.decision
    result: dict[str, object] = {ResultKey.DECISION: decision.kind.value, ResultKey.REASON_CODE: decision.reason.value}
    if decision.amount is not None and line is not None:
        result.update({ResultKey.ITEM_NAME: line.name, ResultKey.QUANTITY: quantity})
    if assessment.dispute is not None:
        result[ResultKey.AMOUNT_DISPUTE] = True
    return result


def _proposal(
    context: TurnContext, check: RefundCheck, decision: Decision, reason: RefundReason
) -> ProposedRefund | None:
    line = check.order.line(check.item_id) if check.order is not None else None
    if check.order is None or line is None or decision.amount is None:
        return None
    if decision.kind is not DecisionKind.NEEDS_CONFIRMATION:
        return None
    already = refunded_quantity(line.item_id, check.order_refunds)
    return ProposedRefund(
        order_id=check.order.order_id,
        item_id=line.item_id,
        item_name=line.name,
        quantity=check.quantity,
        amount=decision.amount,
        reason=reason,
        idempotency_key=idempotency_key(
            context.customer_id, check.order.order_id, line.item_id, check.quantity, already
        ),
    )


class ToolRegistry:
    def __init__(self, engine: PolicyEngine) -> None:
        self._engine = engine
        commands: tuple[Command[Any], ...] = (
            Command(ToolName.LIST_MY_ORDERS, LIST_DESCRIPTION, NoArguments, _list_my_orders),
            Command(ToolName.GET_ORDER, GET_ORDER_DESCRIPTION, GetOrderArguments, _get_order),
            Command(
                ToolName.REQUEST_REFUND,
                REFUND_DESCRIPTION,
                RequestRefundArguments,
                self._request_refund,
            ),
            Command(
                ToolName.ESCALATE_TO_HUMAN,
                ESCALATE_DESCRIPTION,
                NoArguments,
                _escalate_to_human,
            ),
        )
        self._commands: dict[str, Command[Any]] = {command.name: command for command in commands}

    def schemas(self) -> tuple[ToolSchema, ...]:
        return tuple(
            ToolSchema(command.name, command.description, schema_for(command.arguments_type))
            for command in self._commands.values()
        )

    def run(self, call: ToolCall, context: TurnContext) -> ToolOutcome | ToolFault:
        command = self._commands.get(call.name)
        if command is None:
            return ToolFault(ReasonCode.UNKNOWN_TOOL, f"unknown tool: {call.name}")
        arguments = parse_arguments(command.arguments_type, call.arguments_json)
        if isinstance(arguments, ToolFault):
            return arguments
        outcome: ToolOutcome = command.handler(arguments, context)
        return outcome

    def _request_refund(self, arguments: RequestRefundArguments, context: TurnContext) -> ToolOutcome:
        check = refund_check(context, OrderId(arguments.order_id), ItemId(arguments.item_id), arguments.quantity)
        assessment = self._engine.assess_refund(check)
        line = None if check.order is None else check.order.line(check.item_id)
        decision = assessment.decision
        return ToolOutcome(
            result=_refund_result(assessment, line, arguments.quantity),
            decision=decision,
            proposal=_proposal(context, check, decision, arguments.reason),
            escalations=_escalations(assessment, check, line),
            dispute=assessment.dispute,
            shows_refund=decision.reason is ReasonCode.ALREADY_REFUNDED,
        )

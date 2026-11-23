from dataclasses import dataclass

from support_agent.domain.decisions import Decision, ReasonCode
from support_agent.domain.ids import (
    ConversationId,
    CustomerId,
    IdempotencyKey,
    ItemId,
    OrderId,
    RefundId,
    TraceId,
)
from support_agent.domain.money import Money
from support_agent.domain.refunds import RefundReason, RefundState


@dataclass(frozen=True)
class SupportRequest:
    customer_id: CustomerId
    conversation_id: ConversationId
    message: str


@dataclass(frozen=True)
class ProposedRefund:
    order_id: OrderId
    item_id: ItemId
    item_name: str
    quantity: int
    amount: Money
    reason: RefundReason
    idempotency_key: IdempotencyKey


@dataclass(frozen=True)
class ActionOutcome:
    refund_id: RefundId
    order_id: OrderId
    item_id: ItemId
    quantity: int
    amount: Money
    state: RefundState
    replayed: bool = False


@dataclass(frozen=True)
class EscalationItem:
    """One reason to involve a human, tied to the validated order line and record amount it concerns."""

    reason: ReasonCode
    order_id: OrderId | None = None
    item_id: ItemId | None = None
    amount: Money | None = None
    claimed: Money | None = None


@dataclass(frozen=True)
class Escalation:
    reasons: tuple[ReasonCode, ...]
    customer_id: CustomerId
    summary: str
    trace_id: TraceId

    def reason_labels(self) -> str:
        return ", ".join(reason.value for reason in self.reasons)


@dataclass(frozen=True)
class TurnResult:
    reply: str
    trace_id: TraceId
    tool_calls: tuple[str, ...]
    decisions: tuple[Decision, ...]
    proposal: ProposedRefund | None
    actions: tuple[ActionOutcome, ...]
    escalation: Escalation | None

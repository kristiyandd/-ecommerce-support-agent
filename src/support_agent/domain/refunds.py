from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from support_agent.domain.errors import RefundTransitionError
from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId, RefundId, TraceId
from support_agent.domain.money import Money


class RefundReason(StrEnum):
    DAMAGED = "damaged"
    RETURNED = "returned"
    OTHER = "other"


class RefundState(StrEnum):
    ISSUED = "issued"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


ALLOWED_TRANSITIONS: Mapping[RefundState, frozenset[RefundState]] = MappingProxyType(
    {
        RefundState.PENDING_REVIEW: frozenset({RefundState.ISSUED, RefundState.REJECTED}),
        RefundState.ISSUED: frozenset(),
        RefundState.REJECTED: frozenset(),
    }
)


@dataclass(frozen=True)
class RefundRecord:
    refund_id: RefundId
    idempotency_key: IdempotencyKey
    customer_id: CustomerId
    order_id: OrderId
    item_id: ItemId
    quantity: int
    amount: Money
    reason: RefundReason
    state: RefundState
    trace_id: TraceId


def transition(record: RefundRecord, target: RefundState) -> RefundRecord:
    """Move a refund to a new state; a transition outside ALLOWED_TRANSITIONS is a programming error."""
    if target not in ALLOWED_TRANSITIONS[record.state]:
        raise RefundTransitionError(record.state, target)
    return replace(record, state=target)

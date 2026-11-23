from decimal import Decimal

import pytest

from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId, RefundId, TraceId
from support_agent.domain.money import Currency, Money
from support_agent.domain.refunds import RefundReason, RefundRecord, RefundState, transition


def _record(state: RefundState) -> RefundRecord:
    return RefundRecord(
        refund_id=RefundId("R-1"),
        idempotency_key=IdempotencyKey("K-1"),
        customer_id=CustomerId("C-1"),
        order_id=OrderId("O-1"),
        item_id=ItemId("I-1"),
        quantity=1,
        amount=Money(Decimal("1.00"), Currency.EUR),
        reason=RefundReason.OTHER,
        state=state,
        trace_id=TraceId("T-1"),
    )


@pytest.mark.parametrize("target", [RefundState.ISSUED, RefundState.REJECTED])
def test_pending_review_can_be_resolved(target: RefundState) -> None:
    assert transition(_record(RefundState.PENDING_REVIEW), target).state is target


@pytest.mark.parametrize("start", [RefundState.ISSUED, RefundState.REJECTED])
def test_terminal_states_cannot_change(start: RefundState) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        transition(_record(start), RefundState.PENDING_REVIEW)

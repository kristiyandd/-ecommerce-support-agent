"""Executes a confirmed refund proposal after re-checking policy on fresh state."""

import logging
import threading
from collections.abc import Callable

from support_agent.application.context import TurnContext, refund_check
from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import REFUND_ID_PREFIX, CustomerId, RefundId, TraceId
from support_agent.domain.refunds import RefundRecord, RefundState
from support_agent.domain.turn import ActionOutcome, ProposedRefund
from support_agent.policy.engine import PolicyEngine

logger = logging.getLogger(__name__)


def _outcome(record: RefundRecord, *, replayed: bool) -> ActionOutcome:
    return ActionOutcome(
        refund_id=record.refund_id,
        order_id=record.order_id,
        item_id=record.item_id,
        quantity=record.quantity,
        amount=record.amount,
        state=record.state,
        replayed=replayed,
    )


class RefundExecutor:
    def __init__(self, engine: PolicyEngine, new_id: Callable[[], str]) -> None:
        self._engine = engine
        self._new_id = new_id
        self._lock = threading.Lock()

    def execute(self, proposal: ProposedRefund, context: TurnContext, trace_id: TraceId) -> ActionOutcome | Decision:
        with self._lock:
            existing = context.refunds.find_by_key(proposal.idempotency_key)
            if existing is not None:
                return _outcome(existing, replayed=True)
            if not self._still_valid(proposal, context):
                return Decision(DecisionKind.DENY, ReasonCode.CONFIRMATION_STALE)
            record = self._issue(proposal, context.customer_id, trace_id)
            context.refunds.add(record)
        logger.info("refund issued refund_id=%s trace_id=%s", record.refund_id, trace_id)
        return _outcome(record, replayed=False)

    def _still_valid(self, proposal: ProposedRefund, context: TurnContext) -> bool:
        check = refund_check(context, proposal.order_id, proposal.item_id, proposal.quantity)
        decision = self._engine.assess_refund(check).decision
        return decision.kind is DecisionKind.NEEDS_CONFIRMATION and decision.amount == proposal.amount

    def _issue(self, proposal: ProposedRefund, customer_id: CustomerId, trace_id: TraceId) -> RefundRecord:
        return RefundRecord(
            refund_id=RefundId(f"{REFUND_ID_PREFIX}{self._new_id()}"),
            idempotency_key=proposal.idempotency_key,
            customer_id=customer_id,
            order_id=proposal.order_id,
            item_id=proposal.item_id,
            quantity=proposal.quantity,
            amount=proposal.amount,
            reason=proposal.reason,
            state=RefundState.ISSUED,
            trace_id=trace_id,
        )

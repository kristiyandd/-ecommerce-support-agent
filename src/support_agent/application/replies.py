"""All customer-facing sentences written by code: outcomes, money, reason explanations and summaries."""

from collections.abc import Mapping
from types import MappingProxyType

from support_agent.domain.decisions import ReasonCode
from support_agent.domain.ids import TraceId
from support_agent.domain.money import Money
from support_agent.domain.turn import ActionOutcome, EscalationItem, ProposedRefund

TIMES = chr(0xD7)
NONE_LABEL = "none"

DECLINED = "Okay, I haven't made that refund."
CLARIFY = "Sorry, I couldn't work that out. Could you tell me the order number and what you need help with?"
SAFE_FALLBACK = (
    "Sorry, I can't answer that reliably right now. Could you rephrase your question, including the order number?"
)

REPLY_BY_REASON: Mapping[ReasonCode, str] = MappingProxyType(
    {
        ReasonCode.ORDER_NOT_FOUND: "I can't find that order on your account.",
        ReasonCode.ORDER_NOT_ELIGIBLE: "That order isn't eligible for a refund at the moment.",
        ReasonCode.ITEM_NOT_ON_ORDER: "That item isn't on this order.",
        ReasonCode.ALREADY_REFUNDED: "That item has already been refunded.",
        ReasonCode.QUANTITY_EXCEEDS_REFUNDABLE: "That's more units than can still be refunded.",
        ReasonCode.EXCEEDS_AMOUNT_PAID: "That refund would be more than was paid for the order.",
        ReasonCode.CONFIRMATION_STALE: (
            "I couldn't complete that refund because the order details changed since it was proposed; "
            "no money has moved. Please ask again and I'll check the current details."
        ),
        ReasonCode.ABOVE_APPROVAL_THRESHOLD: (
            "Refunds of this size on one order need a colleague's approval, so I haven't refunded it."
        ),
        ReasonCode.CUSTOMER_LIMIT_EXCEEDED: (
            "This is more than I can refund automatically, so a colleague's approval is needed; I haven't refunded it."
        ),
        ReasonCode.LOOP_EXHAUSTED: "I couldn't complete this request automatically; no money has moved.",
        ReasonCode.MODEL_UNAVAILABLE: "I can't complete this request right now; no money has moved.",
        ReasonCode.OUTPUT_BLOCKED: SAFE_FALLBACK,
        ReasonCode.INTERNAL_ERROR: "Something went wrong on our side; no money has moved.",
    }
)


def reason_line(reason: ReasonCode) -> str:
    return REPLY_BY_REASON.get(reason, "")


def confirmation_line(proposal: ProposedRefund) -> str:
    return (
        f"To confirm a refund of {proposal.amount.format()} for {proposal.quantity} {TIMES} {proposal.item_name} "
        f"on order {proposal.order_id}, reply 'yes'."
    )


def dispute_line(claimed: Money, record_amount: Money) -> str:
    return (
        f"The amount you mentioned ({claimed.format()}) is higher than the {record_amount.format()} "
        "our records show for this item; a colleague will review the difference."
    )


def escalation_line(trace_id: TraceId) -> str:
    return f"I've passed this to a colleague, who will follow up with you (reference {trace_id})."


def executed_line(outcome: ActionOutcome, item_name: str) -> str:
    if outcome.replayed:
        return (
            f"That refund was already issued earlier: {outcome.amount.format()} for {outcome.quantity} {TIMES} "
            f"{item_name} on order {outcome.order_id} (refund reference {outcome.refund_id}). Nothing new was charged."
        )
    return (
        f"Done: a refund of {outcome.amount.format()} for {outcome.quantity} {TIMES} {item_name} on order "
        f"{outcome.order_id} has been issued (refund reference {outcome.refund_id})."
    )


def escalation_summary(items: tuple[EscalationItem, ...]) -> str:
    """Code-built summary for the human queue: reason codes, IDs and record amounts only, never free text."""
    return "; ".join(_summary_part(item) for item in items)


def _summary_part(item: EscalationItem) -> str:
    claimed = f", claimed={item.claimed.format()}" if item.claimed else ""
    return (
        f"{item.reason.value}(order={item.order_id or NONE_LABEL}, item={item.item_id or NONE_LABEL}, "
        f"amount={item.amount.format() if item.amount else NONE_LABEL}{claimed})"
    )

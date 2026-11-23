from dataclasses import dataclass
from enum import StrEnum

from support_agent.domain.money import Money


class DecisionKind(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_CONFIRMATION = "needs_confirmation"
    ESCALATE = "escalate"


class ReasonCode(StrEnum):
    ORDER_NOT_FOUND = "order_not_found"
    ORDER_NOT_ELIGIBLE = "order_not_eligible"
    ITEM_NOT_ON_ORDER = "item_not_on_order"
    ALREADY_REFUNDED = "already_refunded"
    QUANTITY_EXCEEDS_REFUNDABLE = "quantity_exceeds_refundable"
    EXCEEDS_AMOUNT_PAID = "exceeds_amount_paid"
    ABOVE_APPROVAL_THRESHOLD = "above_approval_threshold"
    CUSTOMER_LIMIT_EXCEEDED = "customer_limit_exceeded"
    AMOUNT_DISPUTE = "amount_dispute"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMED = "confirmed"
    CONFIRMATION_STALE = "confirmation_stale"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    SECOND_PROPOSAL = "second_proposal"
    LOOP_EXHAUSTED = "loop_exhausted"
    MODEL_UNAVAILABLE = "model_unavailable"
    OUTPUT_BLOCKED = "output_blocked"
    CUSTOMER_REQUESTED_HUMAN = "customer_requested_human"
    NO_ACTION = "no_action"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: ReasonCode
    amount: Money | None = None

    def label(self) -> str:
        return f"{self.kind.value}:{self.reason.value}"

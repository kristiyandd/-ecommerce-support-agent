"""Runs the refund rules in order; the first failing rule decides."""

from dataclasses import dataclass

from support_agent.domain.decisions import Decision, DecisionKind
from support_agent.policy.config import PolicyConfig
from support_agent.policy.rules import RULES, RefundCheck, amount_dispute, confirmation_required

COMPUTED_AMOUNT_KINDS = frozenset({DecisionKind.NEEDS_CONFIRMATION, DecisionKind.ESCALATE})


@dataclass(frozen=True)
class RefundAssessment:
    decision: Decision
    dispute: Decision | None


class PolicyEngine:
    def __init__(self, config: PolicyConfig) -> None:
        self._config = config

    def assess_refund(self, check: RefundCheck) -> RefundAssessment:
        decision = self._decide(check)
        dispute = None
        if decision.kind in COMPUTED_AMOUNT_KINDS and decision.amount is not None:
            dispute = amount_dispute(check, decision.amount)
        return RefundAssessment(decision=decision, dispute=dispute)

    def _decide(self, check: RefundCheck) -> Decision:
        for rule in RULES:
            failure = rule(check, self._config)
            if failure is not None:
                return failure
        return confirmation_required(check)

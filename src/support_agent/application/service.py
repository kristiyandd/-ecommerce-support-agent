"""SupportService: one SupportRequest in, exactly one TurnResult out (Facade over the turn pipeline)."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from support_agent.application import replies
from support_agent.application.audit import AuditKind
from support_agent.application.auditor import Auditor
from support_agent.application.claims import extract_claimed_amounts
from support_agent.application.config import OrchestratorConfig
from support_agent.application.context import ContextBuilder, TurnContext
from support_agent.application.conversation_state import ConversationKey, ConversationState
from support_agent.application.model_protocol import Message, Role
from support_agent.application.orchestrator import AgentLoop, TurnState
from support_agent.application.output_check import AllowedFacts, OutputCheck
from support_agent.application.refund_executor import RefundExecutor
from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import TRACE_ID_PREFIX, TraceId
from support_agent.domain.turn import (
    ActionOutcome,
    Escalation,
    EscalationItem,
    ProposedRefund,
    SupportRequest,
    TurnResult,
)

logger = logging.getLogger(__name__)

NO_ACTION = Decision(DecisionKind.ALLOW, ReasonCode.NO_ACTION)


@dataclass(frozen=True)
class TurnPipeline:
    """The collaborators of a turn: data scope, model loop, refund execution and the output check."""

    context: ContextBuilder
    loop: AgentLoop
    executor: RefundExecutor
    output_check: OutputCheck


class SupportService:
    def __init__(
        self,
        pipeline: TurnPipeline,
        state: ConversationState,
        auditor: Auditor,
        config: OrchestratorConfig,
        new_id: Callable[[], str],
    ) -> None:
        self._pipeline = pipeline
        self._state = state
        self._auditor = auditor
        self._config = config
        self._new_id = new_id

    def handle(self, request: SupportRequest) -> TurnResult:
        trace_id = TraceId(f"{TRACE_ID_PREFIX}{self._new_id()}")
        key: ConversationKey = (request.conversation_id, request.customer_id)
        try:
            self._auditor.record(trace_id, AuditKind.REQUEST, customer_id=request.customer_id, message=request.message)
            result = self._dispatch(request, key, trace_id)
        except Exception as error:
            logger.exception("turn failed trace_id=%s", trace_id)
            self._record_after_the_fact(trace_id, AuditKind.INTERNAL_ERROR, error=type(error).__name__)
            result = self._failed(request, trace_id)
        self._state.conversations.append(
            key, Message(Role.USER, request.message), Message(Role.ASSISTANT, result.reply)
        )
        labels = ", ".join(decision.label() for decision in result.decisions)
        self._record_after_the_fact(trace_id, AuditKind.RESULT, reply=result.reply, decisions=labels)
        return result

    def _record_after_the_fact(self, trace_id: TraceId, kind: AuditKind, /, **payload: object) -> None:
        """Audit once the outcome is fixed: a failing audit is logged but never changes what the customer is told."""
        try:
            self._auditor.record(trace_id, kind, **payload)
        except Exception:
            logger.exception("audit write failed trace_id=%s kind=%s", trace_id, kind)

    def _dispatch(self, request: SupportRequest, key: ConversationKey, trace_id: TraceId) -> TurnResult:
        pending = self._state.pending.take(key)
        if pending is not None and self._is_affirmation(request.message):
            return self._confirm(request, pending, trace_id)
        result = self._converse(request, key, trace_id)
        if pending is None:
            return result
        return replace(result, reply=f"{replies.DECLINED} {result.reply}")

    def _is_affirmation(self, message: str) -> bool:
        return message.strip().lower().rstrip(".!") in self._config.affirmations

    def _failed(self, request: SupportRequest, trace_id: TraceId) -> TurnResult:
        item = EscalationItem(ReasonCode.INTERNAL_ERROR)
        escalation = Escalation((item.reason,), request.customer_id, replies.escalation_summary((item,)), trace_id)
        reply = f"{replies.reason_line(ReasonCode.INTERNAL_ERROR)} {replies.escalation_line(trace_id)}"
        decision = Decision(DecisionKind.ESCALATE, ReasonCode.INTERNAL_ERROR)
        return TurnResult(reply, trace_id, (), (decision,), None, (), escalation)

    def _confirm(self, request: SupportRequest, proposal: ProposedRefund, trace_id: TraceId) -> TurnResult:
        context = self._pipeline.context.build(request.customer_id, ())
        outcome = self._pipeline.executor.execute(proposal, context, trace_id)
        if isinstance(outcome, ActionOutcome):
            decision = Decision(DecisionKind.ALLOW, ReasonCode.CONFIRMED, outcome.amount)
            reply = replies.executed_line(outcome, proposal.item_name)
            result = TurnResult(reply, trace_id, (), (decision,), None, (outcome,), None)
            self._record_after_the_fact(
                trace_id, AuditKind.ACTION, refund_id=outcome.refund_id, replayed=outcome.replayed
            )
            return result
        self._auditor.record(trace_id, AuditKind.DECISION, kind=outcome.kind, reason=outcome.reason)
        return TurnResult(replies.reason_line(outcome.reason), trace_id, (), (outcome,), None, (), None)

    def _converse(self, request: SupportRequest, key: ConversationKey, trace_id: TraceId) -> TurnResult:
        claims = extract_claimed_amounts(request.message, self._pipeline.context.currency)
        context = self._pipeline.context.build(request.customer_id, claims)
        state = TurnState(trace_id, [*self._state.conversations.history(key), Message(Role.USER, request.message)])
        self._pipeline.loop.run(state, context)
        model_text = self._checked_model_text(state, request, context)
        reply = self._compose(model_text, state)
        escalation = self._escalation(state, request)
        if state.proposal is not None:
            self._state.pending.put(key, state.proposal)
        decisions = tuple(state.decisions) or (NO_ACTION,)
        return TurnResult(reply, trace_id, tuple(state.tool_names), decisions, state.proposal, (), escalation)

    def _checked_model_text(self, state: TurnState, request: SupportRequest, context: TurnContext) -> str:
        if state.ended_by is not None:
            return "" if state.escalations else replies.CLARIFY
        text = (state.reply or "").strip()
        has_code_lines = state.proposal is not None or bool(state.escalations) or bool(state.reasons_to_explain())
        if not text:
            return "" if has_code_lines else self._block(state, text)
        check = self._pipeline.output_check
        orders = context.orders.list_orders()
        allowed = AllowedFacts(
            order_ids=frozenset(order.order_id for order in orders) | check.canonical_order_ids(request.message),
            refund_on_record=state.refund_on_record,
            item_names=frozenset(line.name for order in orders for line in order.lines),
        )
        return text if check.check(text, allowed) is None else self._block(state, text)

    def _block(self, state: TurnState, text: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()
        self._auditor.record(
            state.trace_id,
            AuditKind.OUTPUT_CHECK,
            reason=ReasonCode.OUTPUT_BLOCKED,
            reply_sha256=digest,
            length=len(text),
        )
        state.decisions.append(Decision(DecisionKind.DENY, ReasonCode.OUTPUT_BLOCKED))
        state.proposal = None
        return replies.SAFE_FALLBACK

    def _compose(self, model_text: str, state: TurnState) -> str:
        lines = [model_text]
        if model_text != replies.SAFE_FALLBACK:
            lines.extend(replies.reason_line(reason) for reason in state.reasons_to_explain())
        if state.proposal is not None:
            lines.append(replies.confirmation_line(state.proposal))
        lines.extend(self._dispute_lines(state))
        if state.escalations:
            lines.append(replies.escalation_line(state.trace_id))
        return " ".join(dict.fromkeys(line for line in lines if line))

    def _dispute_lines(self, state: TurnState) -> list[str]:
        disputes = (item for item in state.escalations if item.reason is ReasonCode.AMOUNT_DISPUTE)
        return [replies.dispute_line(item.claimed, item.amount) for item in disputes if item.amount and item.claimed]

    def _escalation(self, state: TurnState, request: SupportRequest) -> Escalation | None:
        if not state.escalations:
            return None
        items = tuple(dict.fromkeys(state.escalations))
        summary = replies.escalation_summary(items)
        self._auditor.record(state.trace_id, AuditKind.ESCALATION, summary=summary)
        reasons = tuple(dict.fromkeys(item.reason for item in items))
        return Escalation(reasons, request.customer_id, summary, state.trace_id)

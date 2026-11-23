"""Bounded model/tool loop for one turn. Faults end the loop; nothing here moves money."""

import logging
from dataclasses import dataclass, field

from support_agent.application.audit import AuditKind, serialise
from support_agent.application.auditor import Auditor
from support_agent.application.config import OrchestratorConfig
from support_agent.application.context import TurnContext
from support_agent.application.model_protocol import (
    UNTRUSTED_DATA_KEY,
    Message,
    ModelRequest,
    ModelResponse,
    Role,
    ToolCall,
)
from support_agent.application.ports import ModelClient
from support_agent.application.prompts import SYSTEM_PROMPT
from support_agent.application.tool_schema import ToolFault
from support_agent.application.tools import ToolOutcome, ToolRegistry
from support_agent.domain.decisions import Decision, DecisionKind, ReasonCode
from support_agent.domain.ids import TraceId
from support_agent.domain.turn import EscalationItem, ProposedRefund

logger = logging.getLogger(__name__)

EXPLAINED_KINDS = frozenset({DecisionKind.DENY, DecisionKind.ESCALATE})


@dataclass
class TurnState:
    """Mutable accumulator for one turn; turned into a frozen TurnResult by the service."""

    trace_id: TraceId
    messages: list[Message]
    tool_names: list[str] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    escalations: list[EscalationItem] = field(default_factory=list)
    proposal: ProposedRefund | None = None
    reply: str | None = None
    ended_by: ReasonCode | None = None
    refund_on_record: bool = False

    def end(self, reason: ReasonCode, kind: DecisionKind) -> None:
        self.ended_by = reason
        self.proposal = None
        self.decisions.append(Decision(kind, reason))
        if kind is DecisionKind.ESCALATE:
            self.escalations.append(EscalationItem(reason))

    def reasons_to_explain(self) -> list[ReasonCode]:
        return [decision.reason for decision in self.decisions if decision.kind in EXPLAINED_KINDS]


class AgentLoop:
    def __init__(
        self, model: ModelClient, registry: ToolRegistry, auditor: Auditor, config: OrchestratorConfig
    ) -> None:
        self._model = model
        self._registry = registry
        self._auditor = auditor
        self._config = config

    def run(self, state: TurnState, context: TurnContext) -> None:
        for _ in range(self._config.max_model_steps):
            response = self._complete(state)
            if response is None:
                return
            if not response.tool_calls:
                state.reply = response.text
                return
            state.messages.append(Message(Role.ASSISTANT, response.text or "", response.tool_calls))
            if not all(self._run_tool(call, state, context) for call in response.tool_calls):
                return
        self._auditor.record(state.trace_id, AuditKind.DECISION, reason=ReasonCode.LOOP_EXHAUSTED)
        state.end(ReasonCode.LOOP_EXHAUSTED, DecisionKind.ESCALATE)

    def _complete(self, state: TurnState) -> ModelResponse | None:
        request = ModelRequest(SYSTEM_PROMPT, tuple(state.messages), self._registry.schemas())
        self._auditor.record(state.trace_id, AuditKind.MODEL_CALL, messages=len(request.messages))
        try:
            return self._model.complete(request)
        except Exception as error:  # provider boundary: any SDK or network error ends the turn safely
            logger.exception("model client failed")
            self._auditor.record(state.trace_id, AuditKind.MODEL_ERROR, error=type(error).__name__)
            state.end(ReasonCode.MODEL_UNAVAILABLE, DecisionKind.ESCALATE)
            return None

    def _run_tool(self, call: ToolCall, state: TurnState, context: TurnContext) -> bool:
        self._auditor.record(state.trace_id, AuditKind.TOOL_CALL, name=call.name, arguments=call.arguments_json)
        state.tool_names.append(call.name)
        outcome = self._registry.run(call, context)
        if isinstance(outcome, ToolFault):
            self._auditor.record(state.trace_id, AuditKind.DECISION, reason=outcome.reason, detail=outcome.detail)
            state.end(outcome.reason, DecisionKind.DENY)
            return False
        if outcome.proposal is not None and state.proposal is not None:
            self._auditor.record(state.trace_id, AuditKind.DECISION, reason=ReasonCode.SECOND_PROPOSAL)
            state.end(ReasonCode.SECOND_PROPOSAL, DecisionKind.DENY)
            return False
        self._apply(call, outcome, state)
        return True

    def _apply(self, call: ToolCall, outcome: ToolOutcome, state: TurnState) -> None:
        self._auditor.record(state.trace_id, AuditKind.TOOL_RESULT, name=call.name, result=serialise(outcome.result))
        for decision in (outcome.decision, outcome.dispute):
            if decision is not None:
                state.decisions.append(decision)
                self._auditor.record(state.trace_id, AuditKind.DECISION, kind=decision.kind, reason=decision.reason)
        state.escalations.extend(outcome.escalations)
        state.proposal = outcome.proposal or state.proposal
        state.refund_on_record = state.refund_on_record or outcome.shows_refund
        untrusted = serialise({UNTRUSTED_DATA_KEY: outcome.result})
        state.messages.append(Message(Role.TOOL, untrusted, tool_call_id=call.call_id))

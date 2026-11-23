"""Deterministic stand-in for a language model: keyword intents, generic entity patterns, no store access.

It speaks the same message/tool-call protocol a real model would. Reason explanations, money and outcome
sentences are added by code (application/replies.py), so this model never writes them.
"""

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from support_agent.application.claims import MONEY_PATTERN, strip_id_tokens
from support_agent.application.config import ORDER_ID_PATTERN
from support_agent.application.model_protocol import (
    UNTRUSTED_DATA_KEY,
    Message,
    ModelRequest,
    ModelResponse,
    Role,
    ToolCall,
)
from support_agent.application.replies import TIMES
from support_agent.application.tools import ResultKey, ToolName
from support_agent.domain.decisions import DecisionKind
from support_agent.domain.orders import OrderStatus
from support_agent.domain.refunds import RefundReason

MODEL_ID = "heuristic-mock/v1"
CALL_ID_PREFIX = "call-"
REASON_ARGUMENT = "reason"
NUMBER_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
QUANTITY_PATTERN = re.compile(rf"(?<![\d.,\-])\b(\d+|{'|'.join(NUMBER_WORDS)})\b(?![.,]\d)")
WORD_PATTERN = re.compile(r"[a-z]+")
MIN_TOKEN_LENGTH = 3
PLURAL_ES_ENDINGS = ("sses", "ches", "shes", "xes", "zes")
WORDS_BETWEEN_QUANTITY_AND_ITEM = 4


class Intent(StrEnum):
    HUMAN = "human"
    REFUND = "refund"
    STATUS = "status"
    LIST = "list"
    UNCLEAR = "unclear"


INTENT_KEYWORDS: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    (Intent.HUMAN, re.compile(r"\b(?:human|person|agent|manager)s?\b")),
    (Intent.REFUND, re.compile(r"\b(?:refund|money back|reimburse)")),
    (Intent.STATUS, re.compile(r"\b(?:where|status|track|arrive|delivered)")),
    (Intent.LIST, re.compile(r"\b(?:list|show)\b.*\borders\b|\bmy orders\b")),
)
DAMAGED_PATTERN = re.compile(r"\b(?:broken|broke|damaged|cracked|chipped|smashed|shattered)\b")
RETURNED_PATTERN = re.compile(r"\breturn")

CLARIFY_ORDER = "Which order do you mean? Please send me exactly one order ID."
CLARIFY_ITEM = "Which item from the order is this about?"
CLARIFY_QUANTITY = "How many of that item would you like a refund for?"
CLARIFY_REQUEST = "I can check an order, look into a refund or pass you to a colleague. What would you like?"
NOT_FOUND_REPLY = "I can't find order {order_id} on your account."
STATUS_REPLY = "Order {order_id} is {status}."
SHIPPING_REPLY = " It ships with {carrier}, tracking number {tracking_number}."
NO_ESTIMATE_REPLY = " I don't have a delivery estimate on file."
ORDER_LIST_REPLY = "Your orders: {orders}."
NO_ORDERS_REPLY = "I don't see any orders on your account."
ORDER_LIST_ITEM = "{order_id} ({status})"
OFFER_REPLY = "I can offer a refund for {quantity} " + TIMES + " {item_name} from order {order_id}."
NO_TEXT = ""

type Payload = dict[str, object]


@dataclass(frozen=True)
class _Turn:
    text: str
    results: dict[str, Payload]
    tool_messages: int


def _as_dict(value: object) -> Payload:
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


def _payload(message: Message) -> Payload:
    try:
        return _as_dict(_as_dict(json.loads(message.content)).get(UNTRUSTED_DATA_KEY))
    except ValueError:
        return {}


def _read_turn(messages: tuple[Message, ...]) -> _Turn:
    start = max((index for index, message in enumerate(messages) if message.role is Role.USER), default=0)
    turn = messages[start:]
    names = {call.call_id: call.name for message in turn for call in message.tool_calls}
    results = {
        names[message.tool_call_id]: _payload(message)
        for message in turn
        if message.role is Role.TOOL and message.tool_call_id in names
    }
    text = turn[0].content if turn else ""
    return _Turn(text, results, sum(1 for message in turn if message.role is Role.TOOL))


def _normalise(text: str) -> str:
    return MONEY_PATTERN.sub(" ", strip_id_tokens(text)).lower()


def detect_intent(normalised: str) -> Intent:
    return next((intent for intent, pattern in INTENT_KEYWORDS if pattern.search(normalised)), Intent.UNCLEAR)


def detect_reason(normalised: str) -> RefundReason:
    if DAMAGED_PATTERN.search(normalised):
        return RefundReason.DAMAGED
    return RefundReason.RETURNED if RETURNED_PATTERN.search(normalised) else RefundReason.OTHER


def _stem(token: str) -> str:
    if token.endswith("ss"):
        return token
    if token.endswith(PLURAL_ES_ENDINGS):
        return token[:-2]
    return token[:-1] if token.endswith("s") else token


def _stems(name: str) -> set[str]:
    return {_stem(token) for token in WORD_PATTERN.findall(name.lower()) if len(_stem(token)) >= MIN_TOKEN_LENGTH}


def _number(token: str) -> int:
    return NUMBER_WORDS.index(token) + 1 if token in NUMBER_WORDS else int(token)


def quantity_is_ambiguous(normalised: str) -> bool:
    """Two different numbers ("ordered 2 ... one broke") mean the model must ask, not pick one."""
    return len({_number(match.group(1)) for match in QUANTITY_PATTERN.finditer(normalised)}) > 1


def detect_quantity(normalised: str, item_name: str) -> int | None:
    """A number counts only when the item is named within a few words after it ("two of the glasses")."""
    item_stems = _stems(item_name)
    for match in QUANTITY_PATTERN.finditer(normalised):
        following = WORD_PATTERN.findall(normalised[match.end() :])[:WORDS_BETWEEN_QUANTITY_AND_ITEM]
        if item_stems & {_stem(word) for word in following}:
            value = _number(match.group(1))
            return value if value >= 1 else None
    return None


def _name_matches(name: str, normalised: str) -> bool:
    return any(stem in normalised for stem in _stems(name))


def _lines(order: Payload) -> list[Payload]:
    lines = order.get(ResultKey.LINES)
    return [_as_dict(line) for line in lines] if isinstance(lines, list) else []


def select_line(order: Payload, normalised: str) -> Payload | None:
    lines = _lines(order)
    if len(lines) == 1:
        return lines[0]
    matches = [line for line in lines if _name_matches(str(line.get(ResultKey.NAME, "")), normalised)]
    return matches[0] if len(matches) == 1 else None


def _call(turn: _Turn, name: ToolName, arguments: Payload) -> ModelResponse:
    call = ToolCall(f"{CALL_ID_PREFIX}{turn.tool_messages + 1}", name, json.dumps(arguments))
    return ModelResponse(text=None, tool_calls=(call,))


def _say(text: str) -> ModelResponse:
    return ModelResponse(text=text)


def _status_reply(order_id: str, order: Payload) -> str:
    status = str(order.get(ResultKey.STATUS, "")).replace("_", " ")
    reply = STATUS_REPLY.format(order_id=order_id, status=status)
    shipping = _as_dict(order.get(ResultKey.SHIPPING))
    if shipping:
        reply += SHIPPING_REPLY.format(
            carrier=shipping.get(ResultKey.CARRIER, ""), tracking_number=shipping.get(ResultKey.TRACKING_NUMBER, "")
        )
    return reply + NO_ESTIMATE_REPLY if order.get(ResultKey.STATUS) == OrderStatus.IN_TRANSIT else reply


def _order_list_item(entry: Payload) -> str:
    status = str(entry.get(ResultKey.STATUS, "")).replace("_", " ")
    return ORDER_LIST_ITEM.format(order_id=entry.get(ResultKey.ORDER_ID), status=status)


def _refund_reply(order_id: str, result: Payload) -> str:
    if result.get(ResultKey.DECISION) != DecisionKind.NEEDS_CONFIRMATION:
        return NO_TEXT
    quantity, item_name = result.get(ResultKey.QUANTITY, ""), result.get(ResultKey.ITEM_NAME, "")
    return OFFER_REPLY.format(quantity=quantity, item_name=item_name, order_id=order_id)


class HeuristicModel:
    """ModelClient that reads only the latest user message and this turn's tool results."""

    model_id = MODEL_ID

    def __init__(self, order_id_pattern: str = ORDER_ID_PATTERN) -> None:
        self._order_id = re.compile(order_id_pattern)

    def complete(self, request: ModelRequest) -> ModelResponse:
        turn = _read_turn(request.messages)
        normalised = _normalise(turn.text)
        intent = detect_intent(normalised)
        if intent is Intent.HUMAN:
            return self._human(turn)
        if intent is Intent.UNCLEAR:
            return _say(CLARIFY_REQUEST)
        order_ids = list(dict.fromkeys(self._order_id.findall(turn.text)))
        if intent is Intent.LIST or (intent is Intent.STATUS and not order_ids):
            return self._list(turn)
        if len(order_ids) != 1:
            return _say(CLARIFY_ORDER)
        if intent is Intent.STATUS:
            return self._status(turn, order_ids[0])
        return self._refund(turn, order_ids[0], normalised)

    def _human(self, turn: _Turn) -> ModelResponse:
        if ToolName.ESCALATE_TO_HUMAN in turn.results:
            return _say(NO_TEXT)
        return _call(turn, ToolName.ESCALATE_TO_HUMAN, {})

    def _list(self, turn: _Turn) -> ModelResponse:
        result = turn.results.get(ToolName.LIST_MY_ORDERS)
        if result is None:
            return _call(turn, ToolName.LIST_MY_ORDERS, {})
        orders = result.get(ResultKey.ORDERS)
        entries = [_as_dict(order) for order in orders] if isinstance(orders, list) else []
        if not entries:
            return _say(NO_ORDERS_REPLY)
        return _say(ORDER_LIST_REPLY.format(orders=", ".join(_order_list_item(entry) for entry in entries)))

    def _status(self, turn: _Turn, order_id: str) -> ModelResponse:
        order = turn.results.get(ToolName.GET_ORDER)
        if order is None:
            return _call(turn, ToolName.GET_ORDER, {ResultKey.ORDER_ID: order_id})
        if not order.get(ResultKey.FOUND):
            return _say(NOT_FOUND_REPLY.format(order_id=order_id))
        return _say(_status_reply(order_id, order))

    def _refund(self, turn: _Turn, order_id: str, normalised: str) -> ModelResponse:
        order = turn.results.get(ToolName.GET_ORDER)
        if order is None:
            return _call(turn, ToolName.GET_ORDER, {ResultKey.ORDER_ID: order_id})
        if not order.get(ResultKey.FOUND):
            return _say(NOT_FOUND_REPLY.format(order_id=order_id))
        result = turn.results.get(ToolName.REQUEST_REFUND)
        if result is not None:
            return _say(_refund_reply(order_id, result))
        return self._propose(turn, order_id, order, normalised)

    def _propose(self, turn: _Turn, order_id: str, order: Payload, normalised: str) -> ModelResponse:
        line = select_line(order, normalised)
        if line is None:
            return _say(CLARIFY_ITEM)
        if quantity_is_ambiguous(normalised):
            return _say(CLARIFY_QUANTITY)
        quantity = detect_quantity(normalised, str(line.get(ResultKey.NAME, "")))
        if quantity is None and line.get(ResultKey.QUANTITY) == 1:
            quantity = 1
        if quantity is None:
            return _say(CLARIFY_QUANTITY)
        arguments: Payload = {
            ResultKey.ORDER_ID: order_id,
            ResultKey.ITEM_ID: line.get(ResultKey.ITEM_ID),
            ResultKey.QUANTITY: quantity,
            REASON_ARGUMENT: detect_reason(normalised).value,
        }
        return _call(turn, ToolName.REQUEST_REFUND, arguments)

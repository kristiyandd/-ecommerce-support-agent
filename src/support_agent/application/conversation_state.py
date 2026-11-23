"""Solution-side conversation state: replayed history and single-use pending confirmations."""

from dataclasses import dataclass, field

from support_agent.application.model_protocol import Message
from support_agent.domain.ids import ConversationId, CustomerId
from support_agent.domain.turn import ProposedRefund

type ConversationKey = tuple[ConversationId, CustomerId]


class ConversationStore:
    def __init__(self) -> None:
        self._history: dict[ConversationKey, list[Message]] = {}

    def history(self, key: ConversationKey) -> tuple[Message, ...]:
        return tuple(self._history.get(key, ()))

    def append(self, key: ConversationKey, *messages: Message) -> None:
        self._history.setdefault(key, []).extend(messages)


class PendingConfirmations:
    """At most one proposal per conversation and customer; take() removes it, so it is single use."""

    def __init__(self) -> None:
        self._pending: dict[ConversationKey, ProposedRefund] = {}

    def put(self, key: ConversationKey, proposal: ProposedRefund) -> None:
        self._pending[key] = proposal

    def take(self, key: ConversationKey) -> ProposedRefund | None:
        return self._pending.pop(key, None)


@dataclass(frozen=True)
class ConversationState:
    conversations: ConversationStore = field(default_factory=ConversationStore)
    pending: PendingConfirmations = field(default_factory=PendingConfirmations)

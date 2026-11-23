"""Model message and tool-call protocol, shaped like the Claude and OpenAI tool-use APIs."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

UNTRUSTED_DATA_KEY = "untrusted_data"


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class ModelRequest:
    system_prompt: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSchema, ...]


@dataclass(frozen=True)
class ModelResponse:
    text: str | None
    tool_calls: tuple[ToolCall, ...] = ()

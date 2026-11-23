"""Audit record shape, email masking and the one JSON serialisation used for payloads."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from support_agent.domain.ids import TraceId

EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


class AuditKind(StrEnum):
    REQUEST = "request"
    MODEL_CALL = "model_call"
    MODEL_ERROR = "model_error"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DECISION = "decision"
    ACTION = "action"
    ESCALATION = "escalation"
    OUTPUT_CHECK = "output_check"
    INTERNAL_ERROR = "internal_error"
    RESULT = "result"


@dataclass(frozen=True)
class AuditEntry:
    trace_id: TraceId
    kind: AuditKind
    payload: Mapping[str, str]
    prompt_version: str
    policy_version: str
    model_id: str


def mask_email(text: str) -> str:
    return EMAIL_PATTERN.sub(r"\1***@\2", text)


def serialise(value: object) -> str:
    """One JSON form for audit payloads and tool results sent to the model."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

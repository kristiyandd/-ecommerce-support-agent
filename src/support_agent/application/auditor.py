"""The single writer of audit entries: every value as plain text, every entry with the same stamp."""

from dataclasses import dataclass
from enum import Enum

from support_agent.application.audit import AuditEntry, AuditKind
from support_agent.application.ports import AuditLog
from support_agent.domain.ids import TraceId


@dataclass(frozen=True)
class AuditStamp:
    """What was in force for a decision: the prompt, the policy rules and the model."""

    prompt_version: str
    policy_version: str
    model_id: str


def _text(value: object) -> str:
    return value.value if isinstance(value, Enum) else str(value)


class Auditor:
    def __init__(self, log: AuditLog, stamp: AuditStamp) -> None:
        self._log = log
        self._stamp = stamp

    def record(self, trace_id: TraceId, kind: AuditKind, /, **payload: object) -> None:
        values = {key: _text(value) for key, value in payload.items()}
        stamp = self._stamp
        entry = AuditEntry(trace_id, kind, values, stamp.prompt_version, stamp.policy_version, stamp.model_id)
        self._log.append(entry)

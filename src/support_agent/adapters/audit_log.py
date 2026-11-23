from dataclasses import replace
from types import MappingProxyType

from support_agent.application.audit import AuditEntry, mask_email
from support_agent.domain.ids import TraceId


class InMemoryAuditLog:
    """Append-only; payload values are email-masked on write and read back as immutable tuples."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        masked = {key: mask_email(value) for key, value in entry.payload.items()}
        self._entries.append(replace(entry, payload=MappingProxyType(masked)))

    def entries(self, trace_id: TraceId) -> tuple[AuditEntry, ...]:
        return tuple(entry for entry in self._entries if entry.trace_id == trace_id)

    def all_entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

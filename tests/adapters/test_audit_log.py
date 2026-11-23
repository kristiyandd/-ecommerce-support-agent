from support_agent.adapters.audit_log import InMemoryAuditLog
from support_agent.application.audit import AuditEntry, AuditKind
from support_agent.domain.ids import TraceId


def test_emails_are_masked_on_write() -> None:
    log = InMemoryAuditLog()

    log.append(
        AuditEntry(
            TraceId("T-1"), AuditKind.REQUEST, {"message": "mail me at jane.doe@shop.test"}, "p/v1", "policy/v1", "m-1"
        )
    )

    assert log.entries(TraceId("T-1"))[0].payload["message"] == "mail me at j***@shop.test"


def test_entries_are_filtered_by_trace_and_keep_order() -> None:
    log = InMemoryAuditLog()
    for trace, kind in (("T-1", AuditKind.REQUEST), ("T-2", AuditKind.REQUEST), ("T-1", AuditKind.RESULT)):
        log.append(AuditEntry(TraceId(trace), kind, {}, "p/v1", "policy/v1", "m-1"))

    assert [entry.kind for entry in log.entries(TraceId("T-1"))] == [AuditKind.REQUEST, AuditKind.RESULT]
    assert len(log.all_entries()) == 3

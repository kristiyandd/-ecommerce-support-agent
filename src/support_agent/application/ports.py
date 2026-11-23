"""Ports the application depends on; adapters implement them."""

from typing import Protocol

from support_agent.application.audit import AuditEntry
from support_agent.application.model_protocol import ModelRequest, ModelResponse
from support_agent.domain.ids import CustomerId, IdempotencyKey, OrderId, TraceId
from support_agent.domain.orders import Order
from support_agent.domain.refunds import RefundRecord


class CustomerOrders(Protocol):
    """Orders of exactly one customer; foreign and missing orders both come back as None."""

    def list_orders(self) -> tuple[Order, ...]: ...

    def find_order(self, order_id: OrderId) -> Order | None: ...


class CustomerRefunds(Protocol):
    """Refund records of exactly one customer."""

    def for_order(self, order_id: OrderId) -> tuple[RefundRecord, ...]: ...

    def all(self) -> tuple[RefundRecord, ...]: ...

    def find_by_key(self, key: IdempotencyKey) -> RefundRecord | None: ...

    def add(self, record: RefundRecord) -> None: ...


class CustomerDataFactory(Protocol):
    """Builds repositories scoped to the authenticated customer, never to an ID chosen by the model."""

    def orders_for(self, customer_id: CustomerId) -> CustomerOrders: ...

    def refunds_for(self, customer_id: CustomerId) -> CustomerRefunds: ...


class ModelClient(Protocol):
    """One model completion: messages and tool schemas in, text and/or tool calls out."""

    @property
    def model_id(self) -> str: ...

    def complete(self, request: ModelRequest) -> ModelResponse: ...


class AuditLog(Protocol):
    """Append-only audit trail keyed by trace_id."""

    def append(self, entry: AuditEntry) -> None: ...

    def entries(self, trace_id: TraceId) -> tuple[AuditEntry, ...]: ...

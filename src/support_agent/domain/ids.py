from typing import NewType

CustomerId = NewType("CustomerId", str)
OrderId = NewType("OrderId", str)
ItemId = NewType("ItemId", str)
ConversationId = NewType("ConversationId", str)
TraceId = NewType("TraceId", str)
RefundId = NewType("RefundId", str)
IdempotencyKey = NewType("IdempotencyKey", str)

TRACE_ID_PREFIX = "trace-"
REFUND_ID_PREFIX = "RF-"

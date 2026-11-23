"""Refund quantities and amounts. Only ISSUED records count."""

import hashlib
from collections.abc import Sequence

from support_agent.domain.ids import CustomerId, IdempotencyKey, ItemId, OrderId
from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import OrderLine
from support_agent.domain.refunds import RefundRecord, RefundState

KEY_SEPARATOR = "|"


def _issued(records: Sequence[RefundRecord]) -> list[RefundRecord]:
    return [record for record in records if record.state is RefundState.ISSUED]


def refunded_quantity(item_id: ItemId, records: Sequence[RefundRecord]) -> int:
    return sum(record.quantity for record in _issued(records) if record.item_id == item_id)


def refundable_quantity(line: OrderLine, records: Sequence[RefundRecord]) -> int:
    return max(0, line.quantity - refunded_quantity(line.item_id, records))


def refund_amount(line: OrderLine, quantity: int) -> Money:
    return line.unit_price.times(quantity)


def refunded_total(records: Sequence[RefundRecord], currency: Currency) -> Money:
    total = Money.zero(currency)
    for record in _issued(records):
        total = total + record.amount
    return total


def idempotency_key(
    customer_id: CustomerId, order_id: OrderId, item_id: ItemId, quantity: int, already_refunded: int
) -> IdempotencyKey:
    parts = KEY_SEPARATOR.join([customer_id, order_id, item_id, str(quantity), str(already_refunded)])
    return IdempotencyKey(hashlib.sha256(parts.encode("utf-8")).hexdigest())

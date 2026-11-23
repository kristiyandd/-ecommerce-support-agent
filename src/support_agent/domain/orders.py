from dataclasses import dataclass
from enum import StrEnum

from support_agent.domain.ids import CustomerId, ItemId, OrderId
from support_agent.domain.money import Money


class OrderStatus(StrEnum):
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RETURNED = "returned"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OrderLine:
    item_id: ItemId
    name: str
    quantity: int
    unit_price: Money


@dataclass(frozen=True)
class Shipping:
    carrier: str
    tracking_number: str


@dataclass(frozen=True)
class Order:
    order_id: OrderId
    customer_id: CustomerId
    status: OrderStatus
    total: Money
    lines: tuple[OrderLine, ...]
    shipping: Shipping | None

    def line(self, item_id: ItemId) -> OrderLine | None:
        return next((line for line in self.lines if line.item_id == item_id), None)

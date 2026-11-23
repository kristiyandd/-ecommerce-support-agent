"""The customer-scoped data a turn may see, and the one way a refund check is assembled from it."""

from dataclasses import dataclass

from support_agent.application.ports import CustomerDataFactory, CustomerOrders, CustomerRefunds
from support_agent.domain.ids import CustomerId, ItemId, OrderId
from support_agent.domain.money import Currency, Money
from support_agent.policy.rules import RefundCheck


@dataclass(frozen=True)
class TurnContext:
    customer_id: CustomerId
    orders: CustomerOrders
    refunds: CustomerRefunds
    claimed_amounts: tuple[Money, ...]


def refund_check(context: TurnContext, order_id: OrderId, item_id: ItemId, quantity: int) -> RefundCheck:
    """Used at proposal time and again at execution time, so both see the same inputs."""
    return RefundCheck(
        order=context.orders.find_order(order_id),
        item_id=item_id,
        quantity=quantity,
        claimed_amounts=context.claimed_amounts,
        order_refunds=context.refunds.for_order(order_id),
        customer_refunds=context.refunds.all(),
    )


class ContextBuilder:
    """The only place a data scope is created, always from the authenticated customer_id."""

    def __init__(self, data: CustomerDataFactory, currency: Currency) -> None:
        self._data = data
        self.currency = currency

    def build(self, customer_id: CustomerId, claimed_amounts: tuple[Money, ...]) -> TurnContext:
        return TurnContext(
            customer_id=customer_id,
            orders=self._data.orders_for(customer_id),
            refunds=self._data.refunds_for(customer_id),
            claimed_amounts=claimed_amounts,
        )

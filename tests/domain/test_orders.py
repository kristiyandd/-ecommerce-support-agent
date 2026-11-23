from support_agent.domain.ids import CustomerId, ItemId, OrderId
from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import Order, OrderLine, OrderStatus

LINE = OrderLine(ItemId("I-1"), "Lamp", 1, Money.parse("10.00", Currency.EUR))
ORDER = Order(OrderId("O-1"), CustomerId("C-1"), OrderStatus.DELIVERED, LINE.unit_price, (LINE,), None)


def test_line_finds_item_on_order() -> None:
    assert ORDER.line(ItemId("I-1")) == LINE


def test_line_returns_none_for_item_not_on_order() -> None:
    assert ORDER.line(ItemId("I-2")) is None

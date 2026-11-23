from support_agent.domain.ids import CustomerId, ItemId, OrderId
from support_agent.domain.money import Currency, Money
from support_agent.domain.refunds import RefundState
from support_agent.policy.refund_amounts import (
    idempotency_key,
    refund_amount,
    refundable_quantity,
    refunded_quantity,
    refunded_total,
)

from .conftest import ITEM, build_order, build_record, eur


def test_refunded_quantity_counts_only_issued_records_for_the_item() -> None:
    records = (
        build_record(quantity=1),
        build_record(quantity=5, state=RefundState.PENDING_REVIEW),
        build_record(quantity=7, item_id=ItemId("other")),
    )

    assert refunded_quantity(ITEM, records) == 1


def test_refundable_quantity_is_line_quantity_minus_issued() -> None:
    line = build_order(quantity=3).lines[0]

    assert refundable_quantity(line, (build_record(quantity=1),)) == 2


def test_refundable_quantity_is_never_negative() -> None:
    line = build_order(quantity=1).lines[0]

    assert refundable_quantity(line, (build_record(quantity=4),)) == 0


def test_refund_amount_is_unit_price_times_quantity() -> None:
    line = build_order(price="14.90", quantity=3).lines[0]

    assert refund_amount(line, 2) == eur("29.80")


def test_refunded_total_sums_issued_records_only() -> None:
    records = (build_record("10.00"), build_record("5.50"), build_record("99.00", state=RefundState.REJECTED))

    assert refunded_total(records, Currency.EUR) == eur("15.50")


def test_refunded_total_of_nothing_is_zero() -> None:
    assert refunded_total((), Currency.EUR) == Money.zero(Currency.EUR)


def test_idempotency_key_is_stable_for_the_same_inputs() -> None:
    first = idempotency_key(CustomerId("C"), OrderId("O"), ItemId("I"), 1, 0)
    second = idempotency_key(CustomerId("C"), OrderId("O"), ItemId("I"), 1, 0)

    assert first == second


def test_idempotency_key_is_a_sha256_hex_digest() -> None:
    key = idempotency_key(CustomerId("C"), OrderId("O"), ItemId("I"), 1, 0)

    assert len(key) == 64
    assert int(key, 16) >= 0


def test_idempotency_key_changes_with_already_refunded() -> None:
    first = idempotency_key(CustomerId("C"), OrderId("O"), ItemId("I"), 1, 0)
    second = idempotency_key(CustomerId("C"), OrderId("O"), ItemId("I"), 1, 1)

    assert first != second

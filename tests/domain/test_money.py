from decimal import Decimal

import pytest

from support_agent.domain.money import Currency, Money

EUR = Currency.EUR


def test_parse_from_float_is_exact_to_the_cent() -> None:
    assert Money.parse(14.90, EUR).amount == Decimal("14.90")


def test_times_multiplies_without_float_drift() -> None:
    assert Money.parse("14.90", EUR).times(2) == Money.parse("29.80", EUR)


def test_quantises_half_up() -> None:
    assert Money.parse("0.005", EUR).amount == Decimal("0.01")


def test_addition_and_subtraction() -> None:
    total = Money.parse("54.80", EUR) - Money.parse("14.90", EUR) + Money.zero(EUR)

    assert total == Money.parse("39.90", EUR)


def test_comparisons() -> None:
    small, large = Money.parse("1.00", EUR), Money.parse("2.00", EUR)

    assert small < large
    assert small <= large
    assert large > small
    assert large >= small


def test_mixing_currencies_is_a_programming_error() -> None:
    other = Money(Decimal(1), "USD")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="currency mismatch"):
        _ = Money.parse("1.00", EUR) + other


def test_format_shows_amount_and_currency() -> None:
    assert Money.parse(29.9, EUR).format() == "29.90 EUR"


def test_out_of_range_amount_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="out of range"):
        Money.parse("9" * 30 + ".00", EUR)

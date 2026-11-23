from decimal import Decimal

import pytest

from support_agent.application.claims import extract_claimed_amounts
from support_agent.domain.money import Currency, Money


def amounts(message: str) -> tuple[Decimal, ...]:
    return tuple(money.amount for money in extract_claimed_amounts(message, Currency.EUR))


def test_bare_number_with_two_decimals_uses_given_currency() -> None:
    assert extract_claimed_amounts("I paid 34.90 for it", Currency.EUR) == (Money.parse("34.90", Currency.EUR),)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("refund me €12,50 please", "12.50"),
        ("it was 7.00 EUR", "7.00"),
        ("it was 7.00 eur", "7.00"),
        ("€ 3.20", "3.20"),
        ("(8,05)", "8.05"),
    ],
)
def test_currency_and_decimal_forms(message: str, expected: str) -> None:
    assert amounts(message) == (Decimal(expected),)


def test_multiple_amounts_in_order() -> None:
    assert amounts("was 10.00 then 20,50 EUR") == (Decimal("10.00"), Decimal("20.50"))


@pytest.mark.parametrize(
    "message",
    ["order ORD-200 please", "tracking DHL-ORD100-TEST", "ABC-12.50 is an id", "I want 2 of them", "about 15 apples"],
)
def test_ids_and_integers_are_ignored(message: str) -> None:
    assert amounts(message) == ()


def test_amount_next_to_id_is_still_found() -> None:
    assert amounts("ORD-200 cost 9.99 EUR") == (Decimal("9.99"),)


def test_thousands_style_numbers_are_not_matched() -> None:
    assert amounts("1.234 items") == ()


def test_absurdly_long_numbers_are_not_claims() -> None:
    assert extract_claimed_amounts("I want " + "9" * 30 + ".00 back", Currency.EUR) == ()


def test_amounts_in_another_currency_are_not_euro_claims() -> None:
    assert extract_claimed_amounts("I paid $40.00 or £12.50 or 9.99 USD", Currency.EUR) == ()


def test_whole_amounts_count_when_euros_are_named() -> None:
    assert extract_claimed_amounts("about 15 euros, or €20", Currency.EUR) == (
        Money.parse("15", Currency.EUR),
        Money.parse("20", Currency.EUR),
    )


@pytest.mark.parametrize("message", ["USD 80.00 please", "80.00 dollars", "GBP 12.50", "12.50 pounds"])
def test_other_currency_codes_and_words_are_not_euro_claims(message: str) -> None:
    assert extract_claimed_amounts(message, Currency.EUR) == ()


def test_thousands_separators_are_read() -> None:
    assert extract_claimed_amounts("I paid 1,000.00 for it", Currency.EUR) == (Money.parse("1000.00", Currency.EUR),)

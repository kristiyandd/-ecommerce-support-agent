"""Money written in free text: customer claims (compared with records, never paid) and money in model text."""

import re
from decimal import Decimal

from support_agent.domain.money import Currency, Money

ID_TOKEN_PATTERN = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9-]*\d[A-Z0-9-]*\b")
"""Any ID-shaped token (orders, items, tracking numbers); removed first so its digits are never amounts."""

OTHER_CURRENCY_SYMBOLS = "$\u00a3\u00a5"
OTHER_CURRENCY_CODES = ("USD", "GBP", "JPY", "CHF")
OTHER_CURRENCY_WORDS = r"(?:USD|GBP|JPY|CHF|dollars?|pounds?|yen|francs?|bucks)\b"
NOT_AFTER_OTHER_CURRENCY = rf"(?<![\w.,\-{OTHER_CURRENCY_SYMBOLS}])(?<![{OTHER_CURRENCY_SYMBOLS}]\s)" + "".join(
    rf"(?<!{code}\s)(?<!{code})" for code in OTHER_CURRENCY_CODES
)
NUMBER_WITH_CENTS = r"(\d{1,3}(?:,\d{3})+\.\d{2}|\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,9}[.,]\d{2})"
MONEY_PATTERN = re.compile(
    rf"{NOT_AFTER_OTHER_CURRENCY}(?:€\s?)?{NUMBER_WITH_CENTS}(?![\w-]|[.,]\d)(?!\s?{OTHER_CURRENCY_WORDS})(?:\s?EUR\b)?",
    re.IGNORECASE,
)
"""An amount with cents, optionally marked as euros, never marked as another currency."""

MARKED_WHOLE_AMOUNT = re.compile(
    rf"€\s?(\d{{1,9}})(?![\d.,])|{NOT_AFTER_OTHER_CURRENCY}(\d{{1,9}})\s?(?:EUR|euros?)\b", re.IGNORECASE
)
"""A whole amount that names euros, such as "€60" or "150 euros"."""

SPELLED_NUMBERS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|"
    "sixty|seventy|eighty|ninety|hundred|thousand"
)
CURRENCY_WORDS = r"(?:€|eur|euros?|usd|gbp|chf|jpy|dollars?|pounds?|bucks)"
MONEY_MENTION = re.compile(
    rf"[€$\u00a3\u00a5]\s?\d|\b(?:eur|usd|gbp|chf|jpy)\s?\d|\d\s?{CURRENCY_WORDS}\b"
    rf"|\b(?:{SPELLED_NUMBERS})\s+{CURRENCY_WORDS}\b|\d[.,]\d{{2}}\b(?!\.)",
    re.IGNORECASE,
)
"""Any way of writing an amount; model text may contain none, because code writes every money sentence."""


def strip_id_tokens(text: str) -> str:
    return ID_TOKEN_PATTERN.sub(" ", text)


def _decimal(number: str) -> Decimal:
    """The last separator is the decimal point; any earlier one separates thousands."""
    integer, cents = number[:-3], number[-2:]
    return Decimal(f"{re.sub(r'[.,]', '', integer)}.{cents}")


def amounts_in(text: str) -> tuple[Decimal, ...]:
    cleaned = strip_id_tokens(text)
    with_cents = [_decimal(match.group(1)) for match in MONEY_PATTERN.finditer(cleaned)]
    wholes = [Decimal(match.group(1) or match.group(2)) for match in MARKED_WHOLE_AMOUNT.finditer(cleaned)]
    return tuple(with_cents + wholes)


def extract_claimed_amounts(message: str, currency: Currency) -> tuple[Money, ...]:
    return tuple(Money(amount, currency) for amount in amounts_in(message))


def mentions_money(text: str) -> bool:
    return bool(MONEY_MENTION.search(strip_id_tokens(text)))

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from support_agent.domain.errors import AmountOutOfRangeError, CurrencyMismatchError

CENT = Decimal("0.01")


class Currency(StrEnum):
    EUR = "EUR"


@dataclass(frozen=True, order=False)
class Money:
    """Exact money value; always quantised to cents. Mixing currencies is a programming error."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        try:
            quantised = self.amount.quantize(CENT, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise AmountOutOfRangeError(self.amount) from None
        object.__setattr__(self, "amount", quantised)

    @classmethod
    def parse(cls, value: str | int | float | Decimal, currency: Currency) -> Money:
        return cls(Decimal(str(value)), currency)

    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(Decimal(0), currency)

    def _same_currency(self, other: Money) -> None:
        if self.currency is not other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def times(self, quantity: int) -> Money:
        return Money(self.amount * quantity, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount >= other.amount

    def format(self) -> str:
        return f"{self.amount} {self.currency.value}"

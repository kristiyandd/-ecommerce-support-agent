"""Programming-error exceptions of the domain; business outcomes are Decision values, never these."""


class CurrencyMismatchError(ValueError):
    def __init__(self, left: str, right: str) -> None:
        super().__init__(f"currency mismatch: {left} vs {right}")


class AmountOutOfRangeError(ValueError):
    def __init__(self, amount: object) -> None:
        super().__init__(f"amount out of range: {amount}")


class RefundTransitionError(ValueError):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"refund transition {source} -> {target} is not allowed")

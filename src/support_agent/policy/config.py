"""Refund policy configuration as a plain frozen value; loading and validation live in the adapter."""

from dataclasses import dataclass

from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import OrderStatus


@dataclass(frozen=True)
class PolicyConfig:
    version: str
    currency: Currency
    approval_threshold: Money
    customer_auto_refund_cap: Money
    refundable_statuses: frozenset[OrderStatus]

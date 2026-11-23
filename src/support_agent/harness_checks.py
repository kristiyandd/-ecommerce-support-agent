"""Harness checks: model-independent invariants (from the raw seed) and behaviour expectations."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from support_agent.domain.turn import TurnResult
from support_agent.paths import CONFIG_DIR

type Raw = Mapping[str, Any]

DEFAULT_POLICY_FILE = CONFIG_DIR / "policy.json"
DATE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]|\b(?:today|tomorrow|tonight|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|january|february|march|april|june|july|august|september|october|november|"
    r"december)\b|\bwithin \d+ (?:hours?|days?)\b|\bin \d+ (?:hours?|days?)\b",
    re.IGNORECASE,
)
"""Dates or delivery promises: the records carry none, so any in a reply is invented."""
CLAIM_PATTERN = re.compile(r"\d+[.,]\d{2}\b")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
"""Both patterns are an independent oracle, deliberately simpler than the production ones they check."""
KNOWN_INVARIANTS = frozenset(
    {
        "no_state_change_on_first_turn",
        "no_foreign_data_in_replies",
        "refund_amount_equals_line_price_times_quantity",
        "cumulative_refund_within_line_paid",
        "claimed_amount_never_paid",
        "no_invented_dates_in_replies",
        "refunds_within_policy_limits",
    }
)


@dataclass(frozen=True)
class SeedFacts:
    """Raw seed records and raw policy limits, read independently of the code under test."""

    customers: tuple[Raw, ...]
    orders: tuple[Raw, ...]
    approval_threshold: Decimal
    customer_cap: Decimal


@dataclass(frozen=True)
class Observation:
    """What one finished turn looked like, plus everything the customer typed so far."""

    customer_id: str
    messages: tuple[str, ...]
    result: TurnResult
    refunds: tuple[Raw, ...]
    first_turn: bool


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_seed_facts(seed_dir: Path, policy_path: Path = DEFAULT_POLICY_FILE) -> SeedFacts:
    policy = read_json(policy_path)
    return SeedFacts(
        customers=tuple(read_json(seed_dir / "customers.json")),
        orders=tuple(read_json(seed_dir / "orders.json")),
        approval_threshold=Decimal(policy["approval_threshold"]),
        customer_cap=Decimal(policy["customer_auto_refund_cap"]),
    )


def _money(value: object) -> Decimal:
    return Decimal(str(value).replace(",", "."))


def _line_of(facts: SeedFacts, order_id: str, item_id: str) -> Raw | None:
    for order in facts.orders:
        if order["order_id"] == order_id:
            return next((line for line in order["items"] if line["item_id"] == item_id), None)
    return None


def _order_owner(facts: SeedFacts, order_id: str) -> str | None:
    return next((str(order["customer_id"]) for order in facts.orders if order["order_id"] == order_id), None)


def check_no_state_change(observation: Observation) -> list[str]:
    if observation.first_turn and observation.refunds:
        return [f"state changed on the first turn: {len(observation.refunds)} refund record(s) exist"]
    return []


def _amount_text(value: object) -> str:
    return f"{_money(value):.2f}"


def _foreign_amounts(order: Raw, own_orders: list[Raw]) -> list[str]:
    own = {_amount_text(value) for mine in own_orders for value in _order_amounts(mine)}
    return [text for text in map(_amount_text, _order_amounts(order)) if text not in own]


def _order_amounts(order: Raw) -> list[object]:
    return [order["total"], *(line["unit_price"] for line in order["items"])]


def check_no_invented_dates(observation: Observation) -> list[str]:
    found = DATE_PATTERN.findall(observation.result.reply)
    return [f"reply invents a date or delivery promise: {found}"] if found else []


def _foreign_terms(facts: SeedFacts, customer_id: str, typed: str) -> list[str]:
    own_orders = [order for order in facts.orders if order["customer_id"] == customer_id]
    own_items = {str(line["name"]).lower() for order in own_orders for line in order["items"]}
    terms = [
        str(customer[key])
        for customer in facts.customers
        if customer["customer_id"] != customer_id
        for key in ("name", "email")
    ]
    for order in facts.orders:
        if order["customer_id"] == customer_id:
            continue
        if order["order_id"] not in typed:
            terms.append(str(order["order_id"]))
        terms.extend(str(line["name"]) for line in order["items"] if str(line["name"]).lower() not in own_items)
        terms.extend(_foreign_amounts(order, own_orders))
    return terms


def check_reply_leaks(observation: Observation, facts: SeedFacts) -> list[str]:
    reply = observation.result.reply
    lowered = reply.lower()
    terms = _foreign_terms(facts, observation.customer_id, " ".join(observation.messages))
    failures = [f"reply contains foreign data: {term!r}" for term in terms if term.lower() in lowered]
    failures.extend(f"reply contains an email address: {email!r}" for email in EMAIL_PATTERN.findall(reply))
    return failures


def _line_paid(line: Raw, quantity: int) -> Decimal:
    return _money(line["unit_price"]) * quantity


def _check_record_amount(record: Raw, line: Raw) -> list[str]:
    amount = _money(record["amount"])
    derived = _line_paid(line, int(record["quantity"]))
    if amount != derived:
        return [f"refund {record['item_id']} amount {amount} != price x quantity {derived}"]
    return []


def _check_claimed(record: Raw, line: Raw, claimed: set[Decimal]) -> list[str]:
    amount = _money(record["amount"])
    if amount in claimed and amount != _line_paid(line, int(record["quantity"])):
        return [f"refund {record['item_id']} paid the claimed amount {amount}"]
    return []


def check_refund_records(observation: Observation, facts: SeedFacts) -> list[str]:
    claimed = {_money(match) for message in observation.messages for match in CLAIM_PATTERN.findall(message)}
    failures: list[str] = []
    paid: dict[tuple[str, str], Decimal] = {}
    for record in observation.refunds:
        key = (str(record["order_id"]), str(record["item_id"]))
        line = _line_of(facts, *key)
        if line is None or _order_owner(facts, key[0]) != observation.customer_id:
            failures.append(f"refund {key[1]} on {key[0]} is not on one of the customer's orders")
            continue
        failures += _check_record_amount(record, line) + _check_claimed(record, line, claimed)
        paid[key] = paid.get(key, Decimal(0)) + _money(record["amount"])
        limit = _line_paid(line, int(line["quantity"]))
        if paid[key] > limit:
            failures.append(f"cumulative refund {paid[key]} on {key[1]} exceeds line paid {limit}")
    return failures


def _order_total(facts: SeedFacts, order_id: str) -> Decimal:
    return next((_money(order["total"]) for order in facts.orders if order["order_id"] == order_id), Decimal(0))


def check_policy_limits(observation: Observation, facts: SeedFacts) -> list[str]:
    """No human approves anything in this build, so issued refunds must stay within every automatic limit."""
    per_order: dict[str, Decimal] = {}
    for record in observation.refunds:
        order_id = str(record["order_id"])
        per_order[order_id] = per_order.get(order_id, Decimal(0)) + _money(record["amount"])
    failures = [
        f"refunds on {order_id} ({total}) exceed the order total or the approval threshold"
        for order_id, total in per_order.items()
        if total > min(_order_total(facts, order_id), facts.approval_threshold)
    ]
    customer_total = sum(per_order.values(), Decimal(0))
    if customer_total > facts.customer_cap:
        failures.append(f"customer refunds {customer_total} exceed the automatic cap {facts.customer_cap}")
    return failures


def _names(declared: object) -> set[str]:
    return {str(name) for name in declared} if isinstance(declared, list) else set()


def check_invariants(observation: Observation, facts: SeedFacts, declared: object) -> list[str]:
    failures = [f"unknown invariant in expectations: {name}" for name in _names(declared) - KNOWN_INVARIANTS]
    failures += check_no_state_change(observation)
    failures += check_reply_leaks(observation, facts)
    failures += check_refund_records(observation, facts)
    failures += check_policy_limits(observation, facts)
    failures += check_no_invented_dates(observation)
    return failures


def _check_tools(result: TurnResult, spec: Raw) -> list[str]:
    called = set(result.tool_calls)
    failures = [f"expected tool not called: {tool}" for tool in spec.get("tools_called", []) if tool not in called]
    failures += [f"forbidden tool called: {tool}" for tool in spec.get("tools_forbidden", []) if tool in called]
    return failures


def _check_decisions(result: TurnResult, spec: Raw) -> list[str]:
    kinds = {decision.kind.value for decision in result.decisions}
    reasons = {decision.reason.value for decision in result.decisions}
    wanted_kinds = spec.get("decision_kinds", [])
    failures = [f"expected decision kind missing: {kind}" for kind in wanted_kinds if kind not in kinds]
    absent = spec.get("decision_reasons_absent", [])
    failures += [f"forbidden decision reason present: {reason}" for reason in absent if reason in reasons]
    return failures


def _check_escalation(result: TurnResult, spec: Raw) -> list[str]:
    expected = bool(spec.get("escalation", False))
    escalation = result.escalation
    if expected != (escalation is not None):
        return [f"escalation expected={expected} but got {escalation is not None}"]
    if escalation is None:
        return []
    actual = {reason.value for reason in escalation.reasons}
    wanted = set(spec.get("escalation_reasons", []))
    return [f"escalation reasons {sorted(actual)} lack expected {sorted(wanted - actual)}"] if wanted - actual else []


def check_first_turn(result: TurnResult, spec: Raw) -> list[str]:
    failures = _check_tools(result, spec) + _check_decisions(result, spec) + _check_escalation(result, spec)
    expected = bool(spec.get("proposal", False))
    if expected != (result.proposal is not None):
        failures.append(f"proposal expected={expected} but got {result.proposal is not None}")
    return failures


def _refund_key(refund: Raw) -> tuple[str, str, int, str]:
    return (str(refund["order_id"]), str(refund["item_id"]), int(refund["quantity"]), str(refund["state"]))


def check_final_refunds(refunds: tuple[Raw, ...], expected: list[Raw]) -> list[str]:
    actual = sorted(_refund_key(refund) for refund in refunds)
    wanted = sorted(_refund_key(refund) for refund in expected)
    return [] if actual == wanted else [f"refund records {actual} != expected {wanted}"]

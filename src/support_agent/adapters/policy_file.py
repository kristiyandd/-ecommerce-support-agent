"""Loads the versioned refund policy (config/policy.json) and validates it with pydantic at the boundary."""

import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from support_agent.domain.money import Currency, Money
from support_agent.domain.orders import OrderStatus
from support_agent.paths import CONFIG_DIR
from support_agent.policy.config import PolicyConfig

DEFAULT_POLICY_PATH = CONFIG_DIR / "policy.json"
AMOUNT_PATTERN = r"^\d{1,9}\.\d{2}$"
MAPPING_SOURCE = "mapping"
NOT_AN_OBJECT = "must contain a JSON object"
UNREADABLE = "cannot be read as JSON"


class PolicyFileError(ValueError):
    """The policy file is missing, unreadable or violates the PolicyFile schema."""

    def __init__(self, source: object, problem: str) -> None:
        super().__init__(f"invalid policy config ({source}): {problem}")


class PolicyFile(BaseModel):
    """Shape of config/policy.json; amounts are strings so no float ever touches money."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    currency: Currency
    approval_threshold: str = Field(pattern=AMOUNT_PATTERN)
    customer_auto_refund_cap: str = Field(pattern=AMOUNT_PATTERN)
    refundable_statuses: list[OrderStatus]
    note: str = ""


def policy_config_from_mapping(raw: Mapping[str, object]) -> PolicyConfig:
    try:
        policy = PolicyFile.model_validate(raw)
    except ValidationError as error:
        raise PolicyFileError(MAPPING_SOURCE, str(error)) from None
    return PolicyConfig(
        version=policy.version,
        currency=policy.currency,
        approval_threshold=Money.parse(policy.approval_threshold, policy.currency),
        customer_auto_refund_cap=Money.parse(policy.customer_auto_refund_cap, policy.currency),
        refundable_statuses=frozenset(policy.refundable_statuses),
    )


def load_policy_config(path: Path = DEFAULT_POLICY_PATH) -> PolicyConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PolicyFileError(path, f"{UNREADABLE}: {error}") from error
    if not isinstance(raw, dict):
        raise PolicyFileError(path, NOT_AN_OBJECT)
    return policy_config_from_mapping(raw)

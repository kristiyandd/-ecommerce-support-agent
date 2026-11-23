import json
from pathlib import Path

import pytest

from support_agent.adapters.policy_file import DEFAULT_POLICY_PATH, load_policy_config, policy_config_from_mapping
from support_agent.domain.orders import OrderStatus

from .conftest import eur


def valid_raw() -> dict[str, object]:
    return {
        "version": "policy/test",
        "currency": "EUR",
        "approval_threshold": "20.00",
        "customer_auto_refund_cap": "75.50",
        "refundable_statuses": ["delivered"],
    }


def test_valid_mapping_becomes_a_config() -> None:
    config = policy_config_from_mapping(valid_raw())

    assert config.version == "policy/test"
    assert config.approval_threshold == eur("20.00")
    assert config.customer_auto_refund_cap == eur("75.50")
    assert config.refundable_statuses == frozenset({OrderStatus.DELIVERED})


@pytest.mark.parametrize(
    "key", ["version", "currency", "approval_threshold", "customer_auto_refund_cap", "refundable_statuses"]
)
def test_missing_field_is_rejected(key: str) -> None:
    raw = valid_raw()
    del raw[key]

    with pytest.raises(ValueError, match=key):
        policy_config_from_mapping(raw)


def test_unknown_status_is_rejected() -> None:
    raw = valid_raw()
    raw["refundable_statuses"] = ["teleported"]

    with pytest.raises(ValueError, match="invalid policy config"):
        policy_config_from_mapping(raw)


@pytest.mark.parametrize("statuses", ["delivered", [1], None])
def test_statuses_must_be_a_list_of_strings(statuses: object) -> None:
    raw = valid_raw()
    raw["refundable_statuses"] = statuses

    with pytest.raises(ValueError, match="invalid policy config"):
        policy_config_from_mapping(raw)


def test_unsupported_currency_is_rejected() -> None:
    raw = valid_raw()
    raw["currency"] = "XXX"

    with pytest.raises(ValueError, match="invalid policy config"):
        policy_config_from_mapping(raw)


def test_garbage_amount_is_rejected() -> None:
    raw = valid_raw()
    raw["approval_threshold"] = "lots"

    with pytest.raises(ValueError, match="invalid policy config"):
        policy_config_from_mapping(raw)


def test_negative_amount_is_rejected() -> None:
    raw = valid_raw()
    raw["customer_auto_refund_cap"] = "-1.00"

    with pytest.raises(ValueError, match="invalid policy config"):
        policy_config_from_mapping(raw)


def test_numeric_amount_instead_of_string_is_rejected() -> None:
    raw = valid_raw()
    raw["approval_threshold"] = 50

    with pytest.raises(ValueError, match="invalid policy config"):
        policy_config_from_mapping(raw)


def test_real_policy_file_loads_with_placeholder_thresholds() -> None:
    config = load_policy_config(DEFAULT_POLICY_PATH)

    assert config.version == "policy/v1"
    assert config.approval_threshold == eur("50.00")
    assert config.customer_auto_refund_cap == eur("100.00")
    assert config.refundable_statuses == frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED})


def test_loader_reads_a_custom_path(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(valid_raw()), encoding="utf-8")

    assert load_policy_config(path).approval_threshold == eur("20.00")


def test_loader_rejects_a_non_object_file(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a JSON object"):
        load_policy_config(path)

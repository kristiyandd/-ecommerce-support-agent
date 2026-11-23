import itertools
from collections.abc import Callable

import pytest

from mock_env import MockCommerceEnv
from support_agent.adapters.audit_log import InMemoryAuditLog


@pytest.fixture
def env() -> MockCommerceEnv:
    return MockCommerceEnv()


@pytest.fixture
def audit_log() -> InMemoryAuditLog:
    return InMemoryAuditLog()


@pytest.fixture
def counter_ids() -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"id-{next(counter)}"

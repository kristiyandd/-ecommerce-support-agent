"""Infrastructure smoke checks only: load, store/read, clear, seed unchanged."""

import hashlib

from mock_env import SEED_DIR, MockCommerceEnv


def _seed_digests() -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(SEED_DIR.glob("*.json"))}


def test_seed_data_can_be_loaded() -> None:
    env = MockCommerceEnv()

    assert len(env.customers()) == 2
    assert len(env.orders()) == 4


def test_runtime_data_can_be_stored_and_read() -> None:
    env = MockCommerceEnv()

    env.append_record("scratch", {"key": "value"})

    assert env.records("scratch") == [{"key": "value"}]


def test_runtime_state_can_be_cleared() -> None:
    env = MockCommerceEnv()
    env.append_record("scratch", {"key": "value"})

    env.reset()

    assert env.records("scratch") == []


def test_seed_files_remain_unchanged() -> None:
    before = _seed_digests()
    env = MockCommerceEnv()
    env.customers()[0]["name"] = "changed"
    env.append_record("scratch", {"key": "value"})
    env.reset()

    assert _seed_digests() == before
    assert env.customers()[0]["name"] != "changed"

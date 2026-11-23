"""Read-only seed data plus a free-form in-memory runtime store.

Seed files are only ever read. Every call returns deep copies, so callers cannot
mutate the loaded seed. Runtime records live in process memory only; a new
process (or ``reset()``) starts again from the seed files.
"""

import copy
import json
from pathlib import Path
from typing import Any

SEED_DIR = Path(__file__).parent / "seed"

type Record = dict[str, Any]


def _load_json(path: Path) -> list[Record]:
    with path.open(encoding="utf-8") as handle:
        loaded: list[Record] = json.load(handle)
    return loaded


class MockCommerceEnv:
    def __init__(self, seed_dir: Path = SEED_DIR) -> None:
        self._customers = _load_json(seed_dir / "customers.json")
        self._orders = _load_json(seed_dir / "orders.json")
        self._runtime: dict[str, list[Record]] = {}

    def customers(self) -> list[Record]:
        return copy.deepcopy(self._customers)

    def orders(self) -> list[Record]:
        return copy.deepcopy(self._orders)

    def append_record(self, collection: str, record: Record) -> None:
        """Store any solution-defined record under a collection name; no schema is imposed."""
        self._runtime.setdefault(collection, []).append(copy.deepcopy(record))

    def records(self, collection: str) -> list[Record]:
        return copy.deepcopy(self._runtime.get(collection, []))

    def reset(self) -> None:
        """Clear all runtime records; seed data is untouched."""
        self._runtime.clear()

"""Narrow check on model-written text before it reaches the customer."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from support_agent.application.claims import mentions_money
from support_agent.application.config import OrchestratorConfig
from support_agent.domain.decisions import ReasonCode

FORMAT_CATEGORY = "Cf"
NORMAL_FORM: Final = "NFKC"


@dataclass(frozen=True)
class AllowedFacts:
    order_ids: frozenset[str]
    refund_on_record: bool
    item_names: frozenset[str]


def _without(text: str, names: frozenset[str]) -> str:
    for name in names:
        text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    return text


def normalise(text: str) -> str:
    """NFKC plus removal of invisible format characters, so look-alike spellings cannot slip past."""
    folded = unicodedata.normalize(NORMAL_FORM, text)
    return "".join(char for char in folded if unicodedata.category(char) != FORMAT_CATEGORY)


class OutputCheck:
    """Blocks foreign order IDs, emails, dates, any money amount and invented refund outcomes."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self._order_id = re.compile(config.order_id_mention_pattern, re.IGNORECASE)
        self._email = re.compile(config.email_pattern)
        self._iso_date = re.compile(config.iso_date_pattern)
        self._completed_refund = re.compile(config.completed_refund_pattern, re.IGNORECASE)

    def canonical_order_ids(self, text: str) -> frozenset[str]:
        return frozenset(f"{prefix.upper()}-{number}" for prefix, number in self._order_id.findall(normalise(text)))

    def check(self, reply: str, allowed: AllowedFacts) -> ReasonCode | None:
        text = normalise(reply)
        violations = (
            bool(self.canonical_order_ids(text) - allowed.order_ids),
            bool(self._email.search(text)),
            bool(self._iso_date.search(text)),
            mentions_money(_without(text, allowed.item_names)),
            not allowed.refund_on_record and bool(self._completed_refund.search(text)),
        )
        return ReasonCode.OUTPUT_BLOCKED if any(violations) else None

"""Orchestrator settings: loop bound, confirmation words and the patterns of the output check."""

from dataclasses import dataclass

from support_agent.application.audit import EMAIL_PATTERN

DEFAULT_AFFIRMATIONS = frozenset({"yes", "y", "confirm", "yes please", "yes, please", "yes, please proceed"})
ORDER_ID_PATTERN = r"\bORD-\d+\b"
ORDER_ID_MENTION_PATTERN = r"(?<![\w\-])(ORD)[\s\-\u2010-\u2015]?(\d+)(?![\w\-])"
COMPLETED_REFUND_PATTERN = (
    r"\b(?:has|have|had|was|were|been|is|i|i've|we|we've)\s+(?:now\s+|already\s+|just\s+)?(?:been\s+)?"
    r"(?:refunded|processed|issued|sent back|credited|paid out|reimbursed|approved|granted|completed?|done|confirmed)\b"
    r"|\brefund (?:processed|issued|approved|granted|completed?|done|confirmed)\b"
    r"|\bon its way\b|\byou(?:'ll| will) (?:receive|get)\b"
)


@dataclass(frozen=True)
class OrchestratorConfig:
    max_model_steps: int = 4
    affirmations: frozenset[str] = DEFAULT_AFFIRMATIONS
    order_id_pattern: str = ORDER_ID_PATTERN
    order_id_mention_pattern: str = ORDER_ID_MENTION_PATTERN
    email_pattern: str = EMAIL_PATTERN.pattern
    iso_date_pattern: str = r"\b\d{4}-\d{2}-\d{2}\b"
    completed_refund_pattern: str = COMPLETED_REFUND_PATTERN

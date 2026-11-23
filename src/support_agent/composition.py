"""Composition root: the only place concrete classes are wired together."""

import itertools
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from mock_env import MockCommerceEnv
from support_agent.adapters.heuristic_model import HeuristicModel
from support_agent.adapters.mock_env_data import MockEnvDataFactory
from support_agent.adapters.policy_file import load_policy_config
from support_agent.application.auditor import Auditor, AuditStamp
from support_agent.application.config import OrchestratorConfig
from support_agent.application.context import ContextBuilder
from support_agent.application.conversation_state import ConversationState
from support_agent.application.orchestrator import AgentLoop
from support_agent.application.output_check import OutputCheck
from support_agent.application.ports import AuditLog, ModelClient
from support_agent.application.prompts import SYSTEM_PROMPT_VERSION
from support_agent.application.refund_executor import RefundExecutor
from support_agent.application.service import SupportService, TurnPipeline
from support_agent.application.tools import ToolRegistry
from support_agent.policy.config import PolicyConfig
from support_agent.policy.engine import PolicyEngine

PROVIDER_VARIABLE = "MODEL_PROVIDER"
MOCK_PROVIDER = "mock"
UUID_ID_LENGTH = 12
COUNTER_ID_PREFIX = "id-"


class UnknownProviderError(ValueError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"unknown {PROVIDER_VARIABLE} '{provider}'; only '{MOCK_PROVIDER}' is implemented")


@dataclass(frozen=True)
class ServiceSettings:
    policy: PolicyConfig | None = None
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)


def uuid_ids() -> Callable[[], str]:
    return lambda: uuid.uuid4().hex[:UUID_ID_LENGTH]


def counter_ids() -> Callable[[], str]:
    """Deterministic IDs for evaluation runs and tests."""
    counter = itertools.count(1)
    return lambda: f"{COUNTER_ID_PREFIX}{next(counter)}"


def create_model(provider: str, config: OrchestratorConfig | None = None) -> ModelClient:
    if provider == MOCK_PROVIDER:
        return HeuristicModel((config or OrchestratorConfig()).order_id_pattern)
    raise UnknownProviderError(provider)


def build_service(
    env: MockCommerceEnv,
    model: ModelClient,
    *,
    audit_log: AuditLog,
    new_id: Callable[[], str],
    settings: ServiceSettings | None = None,
) -> SupportService:
    chosen = settings or ServiceSettings()
    policy = chosen.policy or load_policy_config()
    config = chosen.orchestrator
    engine = PolicyEngine(policy)
    auditor = Auditor(audit_log, AuditStamp(SYSTEM_PROMPT_VERSION, policy.version, model.model_id))
    pipeline = TurnPipeline(
        context=ContextBuilder(MockEnvDataFactory(env), policy.currency),
        loop=AgentLoop(model, ToolRegistry(engine), auditor, config),
        executor=RefundExecutor(engine, new_id),
        output_check=OutputCheck(config),
    )
    return SupportService(pipeline, ConversationState(), auditor, config, new_id)

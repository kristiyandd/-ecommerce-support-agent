"""Trust boundary for model tool calls: pydantic argument models, strict validation and JSON Schema."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, ValidationError

from support_agent.domain.decisions import ReasonCode


class ToolArguments(BaseModel):
    """Base for tool argument models: unknown fields, coercion and mutation are all rejected."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


@dataclass(frozen=True)
class ToolFault:
    reason: ReasonCode
    detail: str


def schema_for(arguments_type: type[ToolArguments]) -> dict[str, object]:
    return arguments_type.model_json_schema()


def _summary(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, item['loc'])) or 'arguments'}: {item['msg']}" for item in error.errors())


def parse_arguments[T: ToolArguments](arguments_type: type[T], arguments_json: str) -> T | ToolFault:
    try:
        return arguments_type.model_validate_json(arguments_json)
    except ValidationError as error:
        return ToolFault(ReasonCode.INVALID_ARGUMENTS, _summary(error))

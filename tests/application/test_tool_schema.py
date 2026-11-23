from enum import StrEnum

import pytest
from pydantic import Field

from support_agent.application.tool_schema import ToolArguments, ToolFault, parse_arguments, schema_for
from support_agent.domain.decisions import ReasonCode


class Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


class Sample(ToolArguments):
    label: str
    count: int = Field(ge=1)
    colour: Colour


class Empty(ToolArguments):
    pass


VALID = '{"label": "x", "count": 2, "colour": "red"}'


def test_schema_requires_every_field_and_forbids_extras() -> None:
    schema = schema_for(Sample)

    assert schema["type"] == "object"
    assert schema["required"] == ["label", "count", "colour"]
    assert schema["additionalProperties"] is False


def test_schema_carries_minimum_and_enum_values() -> None:
    schema = schema_for(Sample)

    assert schema["properties"]["count"] == {"type": "integer", "minimum": 1, "title": "Count"}  # type: ignore[index]
    assert schema["$defs"]["Colour"]["enum"] == ["red", "blue"]  # type: ignore[index]


def test_schema_for_no_arguments_has_no_properties() -> None:
    schema = schema_for(Empty)

    assert schema["properties"] == {}
    assert schema["additionalProperties"] is False


def test_valid_arguments_parse() -> None:
    assert parse_arguments(Sample, VALID) == Sample(label="x", count=2, colour=Colour.RED)


def test_empty_object_parses_for_no_arguments() -> None:
    assert parse_arguments(Empty, "{}") == Empty()


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1, 2]",
        '"text"',
        '{"label": "x", "count": 2}',
        '{"label": "x", "count": 2, "colour": "red", "amount": 5}',
        '{"label": 5, "count": 2, "colour": "red"}',
        '{"label": "x", "count": "2", "colour": "red"}',
        '{"label": "x", "count": 2.0, "colour": "red"}',
        '{"label": "x", "count": true, "colour": "red"}',
        '{"label": "x", "count": 0, "colour": "red"}',
        '{"label": "x", "count": 2, "colour": "green"}',
        '{"label": "x", "count": 2, "colour": 3}',
    ],
)
def test_invalid_arguments_are_faults(raw: str) -> None:
    result = parse_arguments(Sample, raw)
    assert isinstance(result, ToolFault)
    assert result.reason is ReasonCode.INVALID_ARGUMENTS
    assert result.detail

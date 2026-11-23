from collections.abc import Sequence

from support_agent.application.model_protocol import ModelRequest, ModelResponse


class ScriptedModel:
    """Fake ModelClient replaying a fixed script; an Exception step is raised to simulate a provider failure."""

    model_id = "scripted-fake"

    def __init__(self, script: Sequence[ModelResponse | Exception]) -> None:
        self._script = list(script)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        step = self._script.pop(0) if self._script else ModelResponse(text=None)
        if isinstance(step, Exception):
            raise step
        return step

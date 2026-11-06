"""Queued model replies for tests."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.llm.stats import CallStats


class FakeClient:
    def __init__(self, responses: list[str | Exception], *, available: bool = True) -> None:
        self._responses = list(responses)
        self._available = available
        self.calls: list[tuple[str, str]] = []

    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> tuple[T, CallStats]:
        self.calls.append((system, user))
        item = self._pop()
        if isinstance(item, Exception):
            raise item
        try:
            parsed = schema.model_validate_json(item)
        except ValidationError as exc:
            raise LLMOutputInvalid(item) from exc
        return parsed, _stats()

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        self.calls.append((system, user))
        item = self._pop()
        if isinstance(item, Exception):
            raise item
        return item, _stats()

    def is_available(self) -> bool:
        return self._available

    def _pop(self) -> str | Exception:
        if not self._responses:
            raise LLMUnavailable("fake client has no queued response")
        return self._responses.pop(0)


def _stats() -> CallStats:
    return CallStats(
        backend="fake",
        model="fake",
        prompt_tokens=None,
        output_tokens=None,
        total_ms=0.0,
        load_ms=None,
        retries=0,
    )

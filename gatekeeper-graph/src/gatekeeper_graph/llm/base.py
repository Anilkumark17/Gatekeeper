"""The only interface other modules use to talk to a model."""

from typing import Protocol

from pydantic import BaseModel

from gatekeeper_graph.llm.stats import CallStats


class LLMClient(Protocol):
    def generate_structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> tuple[T, CallStats]:
        """Return a validated model and the call stats."""

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        """Return plain text and the call stats."""

    def is_available(self) -> bool:
        """True when this client can accept a call right now."""

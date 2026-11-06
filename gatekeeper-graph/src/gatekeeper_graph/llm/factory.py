"""Pick the client named by LLMConfig."""

from __future__ import annotations

from typing import assert_never

from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.llm.config import LLMConfig, load_config
from gatekeeper_graph.llm.ollama_http import OllamaHttpClient


def make_client(config: LLMConfig | None = None) -> LLMClient:
    """Return the client for config, or for load_config() when config is omitted."""
    resolved = load_config() if config is None else config
    if resolved.provider == "ollama_http":
        return OllamaHttpClient(resolved)
    if resolved.provider == "langchain_ollama" or resolved.provider == "langchain_groq":
        from gatekeeper_graph.llm.langchain_client import LangChainClient

        return LangChainClient(resolved)
    assert_never(resolved.provider)

import pytest

from gatekeeper_graph.llm import LLMConfig, make_client
from gatekeeper_graph.llm.errors import LLMUnavailable
from gatekeeper_graph.llm.ollama_http import OllamaHttpClient


def test_default_provider_is_ollama_http() -> None:
    client = make_client(LLMConfig())
    assert isinstance(client, OllamaHttpClient)


def test_groq_without_api_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable, match="GROQ_API_KEY"):
        make_client(LLMConfig(provider="langchain_groq", model="qwen/qwen3.8-27b"))

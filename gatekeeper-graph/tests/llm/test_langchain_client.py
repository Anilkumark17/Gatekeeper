import pytest
from pydantic import BaseModel, ValidationError

from gatekeeper_graph.llm import LLMConfig
from gatekeeper_graph.llm.errors import LLMOutputInvalid
from gatekeeper_graph.llm.langchain_client import LangChainClient


class Ok(BaseModel):
    ok: bool


class _Runner:
    def __init__(self, results: list[object]) -> None:
        self._results = results
        self.calls = 0

    def invoke(self, messages: object) -> object:
        self.calls += 1
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Chat:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.runner = _Runner([Ok(ok=True)])

    def with_structured_output(self, schema: type[BaseModel], method: str) -> _Runner:
        assert method == "json_schema"
        assert schema is Ok
        return self.runner

    def invoke(self, messages: object) -> object:
        return type("Message", (), {"content": "hello", "usage_metadata": None})()


def test_structured_output_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langchain_ollama")
    monkeypatch.setattr("langchain_ollama.ChatOllama", _Chat)
    client = LangChainClient(LLMConfig(provider="langchain_ollama", retries=1))
    value, stats = client.generate_structured("system", "user", Ok)
    assert value.ok is True
    assert stats.backend == "langchain_ollama"
    assert stats.prompt_tokens is None
    assert stats.retries == 0


def test_validation_error_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langchain_ollama")
    error = ValidationError.from_exception_data(
        "Ok",
        [{"type": "missing", "loc": ("ok",), "input": {}}],
    )

    class RetryChat(_Chat):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.runner = _Runner([error, Ok(ok=True)])

    monkeypatch.setattr("langchain_ollama.ChatOllama", RetryChat)
    client = LangChainClient(LLMConfig(provider="langchain_ollama", retries=1))
    value, stats = client.generate_structured("system", "user", Ok)
    assert value.ok is True
    assert stats.retries == 1


class BadRequestError(Exception):
    """Stand-in for groq.BadRequestError when JSON validation fails."""


def test_json_validate_failed_retries_then_accepts(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langchain_ollama")
    error = BadRequestError("json_validate_failed")

    class RetryChat(_Chat):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.runner = _Runner([error, Ok(ok=True)])

    monkeypatch.setattr("langchain_ollama.ChatOllama", RetryChat)
    client = LangChainClient(LLMConfig(provider="langchain_ollama", retries=1))
    value, stats = client.generate_structured("system", "user", Ok)
    assert value.ok is True
    assert stats.retries == 1


def test_json_validate_failed_twice_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langchain_ollama")

    class RetryChat(_Chat):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.runner = _Runner(
                [BadRequestError("json_validate_failed"), BadRequestError("again")]
            )

    monkeypatch.setattr("langchain_ollama.ChatOllama", RetryChat)
    client = LangChainClient(LLMConfig(provider="langchain_ollama", retries=1))
    with pytest.raises(LLMOutputInvalid):
        client.generate_structured("system", "user", Ok)

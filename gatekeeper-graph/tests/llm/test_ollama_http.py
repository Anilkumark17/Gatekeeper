import json

import httpx
import pytest
from pydantic import BaseModel

from gatekeeper_graph.llm import LLMConfig
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.llm.ollama_http import OllamaHttpClient


class Ok(BaseModel):
    ok: bool


def _config() -> LLMConfig:
    return LLMConfig(retries=1, timeout_s=1)


def _client(handler: httpx.MockTransport) -> OllamaHttpClient:
    return OllamaHttpClient(_config(), transport=handler)


def _payload(text: str) -> dict[str, object]:
    return {
        "response": text,
        "prompt_eval_count": 11,
        "eval_count": 4,
        "total_duration": 2_500_000_000,
        "load_duration": 500_000_000,
    }


def test_structured_success_and_request_body() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(200, json=_payload('{"ok": true}'))

    value, stats = _client(httpx.MockTransport(handler)).generate_structured("system", "user", Ok)
    body = seen[0]
    assert value.ok is True
    assert body["stream"] is False
    assert body["keep_alive"] == "30m"
    assert body["options"] == {"temperature": 0.0, "num_ctx": 2048, "num_predict": 256}
    schema = body["format"]
    assert isinstance(schema, dict)
    assert schema["properties"]["ok"]["type"] == "boolean"
    assert body["prompt"] == "system\n\n---\n\nuser"
    assert stats.prompt_tokens == 11
    assert stats.output_tokens == 4
    assert stats.total_ms == 2500.0
    assert stats.load_ms == 500.0
    assert stats.retries == 0
    assert stats.backend == "ollama_http"


def test_invalid_json_then_valid_retries_once() -> None:
    replies = iter(["not-json", '{"ok": true}'])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload(next(replies)))

    value, stats = _client(httpx.MockTransport(handler)).generate_structured("system", "user", Ok)
    assert value.ok is True
    assert stats.retries == 1


def test_invalid_json_twice_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload("not-json"))

    with pytest.raises(LLMOutputInvalid) as caught:
        _client(httpx.MockTransport(handler)).generate_structured("system", "user", Ok)
    assert caught.value.raw == "not-json"


def test_connection_error_raises_after_retries() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMUnavailable):
        _client(httpx.MockTransport(handler)).generate_text("system", "user")
    assert calls["count"] == 2


def test_is_available_true_and_false() -> None:
    def listed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:3b"}]})

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "other:latest"}]})

    assert _client(httpx.MockTransport(listed)).is_available() is True
    assert _client(httpx.MockTransport(missing)).is_available() is False

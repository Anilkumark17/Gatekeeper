import pytest
from pydantic import BaseModel

from gatekeeper_graph.llm import FakeClient
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable


class Ok(BaseModel):
    ok: bool


def test_queued_outputs_are_recorded() -> None:
    client = FakeClient(['{"ok": true}', "plain"])
    value, structured_stats = client.generate_structured("system", "user", Ok)
    text, text_stats = client.generate_text("system-2", "user-2")
    assert value.ok is True
    assert text == "plain"
    assert structured_stats.backend == "fake"
    assert text_stats.prompt_tokens is None
    assert client.calls == [("system", "user"), ("system-2", "user-2")]


def test_exception_passthrough() -> None:
    client = FakeClient([LLMUnavailable("down")])
    with pytest.raises(LLMUnavailable, match="down"):
        client.generate_text("system", "user")
    assert client.calls == [("system", "user")]


def test_schema_validation() -> None:
    client = FakeClient(["not-json"])
    with pytest.raises(LLMOutputInvalid) as caught:
        client.generate_structured("system", "user", Ok)
    assert caught.value.raw == "not-json"
    assert client.calls == [("system", "user")]

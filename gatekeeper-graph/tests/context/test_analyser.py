import contextlib
import json

import pytest
from pydantic import BaseModel, ValidationError

from gatekeeper_graph.context.analyser_llm import _SYSTEM, LlmIntentOut, analyse_llm
from gatekeeper_graph.context.prepass import prepass
from gatekeeper_graph.llm import FakeClient, LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.llm.stats import CallStats


def _valid() -> str:
    return json.dumps(
        {
            "problem_type": "bug",
            "observed": "Wrong Order",
            "expected": None,
            "key_phrases": ["Invoice", "one two three four five", "invoice", "city"],
            "confidence": "medium",
        }
    )


def test_llm_maps_response_and_merges_prepass() -> None:
    facts = prepass('see `helper` in src/note.js and "bad total"')
    intent, stats = analyse_llm("the invoice is wrong", facts, FakeClient([_valid()]))
    assert intent.problem_type.value == "bug"
    assert intent.source == "llm"
    assert intent.observed == "Wrong Order"
    assert "one two three four five" not in intent.key_phrases
    assert "invoice" in intent.key_phrases
    assert intent.backtick_names == ("helper",)
    assert intent.quoted_text == ("bad total",)
    assert stats.backend == "fake"
    lowered = tuple(phrase.lower() for phrase in intent.key_phrases)
    assert intent.key_phrases == tuple(dict.fromkeys(lowered))


def test_prompt_ends_with_the_question_and_examples_are_generic() -> None:
    question = "the invoice is wrong"
    client = FakeClient([_valid()])
    analyse_llm(question, prepass(question), client)
    system, user = client.calls[0]
    assert user.rstrip().endswith(question)
    assert "Question:\n" + question in user
    for banned in ("titleCase", "receipt", "checkout", "discount", "lineFor"):
        assert banned not in system
        assert banned not in _SYSTEM


def test_invalid_then_valid_is_returned_by_the_client() -> None:
    class RetryClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def generate_structured[T: BaseModel](
            self,
            system: str,
            user: str,
            schema: type[T],
        ) -> tuple[T, CallStats]:
            self.calls.append((system, user))
            with contextlib.suppress(ValidationError):
                schema.model_validate_json("not-json")
            parsed = schema.model_validate_json(_valid())
            return parsed, CallStats(
                backend="fake",
                model="fake",
                prompt_tokens=None,
                output_tokens=None,
                total_ms=0.0,
                load_ms=None,
                retries=1,
            )

        def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
            raise LLMUnavailable("unused")

        def is_available(self) -> bool:
            return True

    question = "the invoice is wrong"
    intent, stats = analyse_llm(question, prepass(question), RetryClient())
    assert isinstance(intent, object)
    assert stats.retries == 1


def test_errors_propagate() -> None:
    with pytest.raises(LLMUnavailable):
        analyse_llm("the invoice is wrong", prepass("x"), FakeClient([LLMUnavailable("down")]))
    with pytest.raises(LLMOutputInvalid):
        analyse_llm("the invoice is wrong", prepass("x"), FakeClient(["not-json"]))


def test_schema_accepts_null_observed() -> None:
    parsed = LlmIntentOut.model_validate_json(_valid())
    assert parsed.expected is None

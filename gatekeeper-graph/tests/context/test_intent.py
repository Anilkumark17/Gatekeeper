import pytest
from pydantic import ValidationError

from gatekeeper_graph.context.intent import Confidence, Intent, ProblemType, StackFrame


def _intent(**overrides: object) -> Intent:
    payload: dict[str, object] = {
        "question": "the total is wrong",
        "problem_type": ProblemType.BUG,
        "confidence": Confidence.LOW,
        "source": "rules",
    }
    payload.update(overrides)
    return Intent.model_validate(payload)


def test_intent_round_trip_and_phrase_cleanup() -> None:
    intent = _intent(key_phrases=(" Receipt ", "receipt", "letter case"))
    assert intent.key_phrases == ("receipt", "letter case")
    restored = Intent.model_validate_json(intent.model_dump_json())
    assert restored == intent


def test_intent_is_frozen() -> None:
    intent = _intent()
    with pytest.raises(ValidationError):
        intent.question = "changed"  # type: ignore[misc]


def test_intent_rejects_long_phrase_and_extra_field() -> None:
    with pytest.raises(ValidationError):
        _intent(key_phrases=("one two three four five",))
    with pytest.raises(ValidationError):
        _intent(extra=True)


def test_intent_rejects_more_than_six_phrases_and_bad_files() -> None:
    with pytest.raises(ValidationError):
        _intent(key_phrases=tuple(f"word{i}" for i in range(7)))
    with pytest.raises(ValidationError):
        _intent(files=(r"src\receipt.js",))
    frame = StackFrame(name="lineFor", file="src/receipt.js", line=4)
    assert frame.line == 4

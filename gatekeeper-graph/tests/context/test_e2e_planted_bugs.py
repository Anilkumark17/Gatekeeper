from pathlib import Path

import pytest
from pydantic import BaseModel

from gatekeeper_graph.context.eval_context import evaluate_context
from gatekeeper_graph.llm.stats import CallStats
from tests.context.conftest import SHOP, groq_configured


class _Scripted:
    """Answers from the question text. Picks stay inside the supplied shortlist."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate_structured[T: BaseModel](
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, CallStats]:
        self.calls.append((system, user))
        if schema.__name__ == "LlmIntentOut":
            payload: dict[str, object] = _intent_payload(user)
        else:
            picks = [{"n": number, "reason": "likely involved"} for number in range(1, 9)]
            payload = {"picks": picks}
        return schema.model_validate(payload), _stats()

    def generate_text(self, system: str, user: str) -> tuple[str, CallStats]:
        self.calls.append((system, user))
        return "{}", _stats()

    def is_available(self) -> bool:
        return True


def _intent_payload(user: str) -> dict[str, object]:
    if "too high" in user:
        phrases = ["checkout", "total"]
        observed = "total too high"
    elif "too small" in user or "discount" in user:
        phrases = ["discount"]
        observed = "discount too small"
    else:
        phrases = ["receipt", "customer name", "letter case"]
        observed = "wrong case"
    return {
        "problem_type": "bug",
        "observed": observed,
        "expected": None,
        "key_phrases": phrases,
        "confidence": "medium",
    }


def _stats() -> CallStats:
    return CallStats(
        backend="fake",
        model="fake",
        prompt_tokens=None,
        output_tokens=None,
        total_ms=1.0,
        load_ms=None,
        retries=0,
    )


def test_planted_bugs_with_fake_client(tmp_path: Path) -> None:
    report = evaluate_context(SHOP, _Scripted(), tmp_path)
    failed = [item for item in report.scenarios if not item.recall]
    assert not failed, report.render()


@pytest.mark.ollama
def test_planted_bugs_with_groq(tmp_path: Path) -> None:
    if not groq_configured():
        pytest.skip("Groq is not configured")
    from gatekeeper_graph.llm import make_client

    report = evaluate_context(SHOP, make_client(), tmp_path)
    destination = Path("docs/verification/context_eval.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report.render(), encoding="utf-8")
    print(report.render())

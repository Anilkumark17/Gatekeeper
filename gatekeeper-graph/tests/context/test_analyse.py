import json

import pytest

from gatekeeper_graph.context.analyse import analyse
from gatekeeper_graph.context.analyser_rules import analyse_rules
from gatekeeper_graph.context.eval_intent import LabelledPrompt, evaluate_intents, load_labelled
from gatekeeper_graph.context.prepass import prepass
from gatekeeper_graph.llm import FakeClient
from gatekeeper_graph.llm.errors import LLMUnavailable
from gatekeeper_graph.store import load_graph
from tests.context.conftest import GOLDEN

_CASES = [
    ("what uses the helper", "impact"),
    ("the total is wrong", "bug"),
    ("add a footer", "change"),
    ("explain the helper", "explain"),
    ("hello there", "unknown"),
    ("at src/main.js:10:1 it failed", "bug"),
]


@pytest.mark.parametrize(("question", "expected"), _CASES)
def test_rules_table(question: str, expected: str) -> None:
    intent = analyse_rules(question, prepass(question, frozenset({"src/main.js"})))
    assert intent.problem_type.value == expected
    assert intent.source == "rules"


def test_explicit_prompt_does_not_call_the_client() -> None:
    client = FakeClient([])
    result = analyse("explain `checkout`", load_graph(GOLDEN), client)
    assert client.calls == []
    assert result.route == "rules"
    assert result.stats is None
    assert result.intent.problem_type.value == "explain"
    assert "checkout" in result.intent.key_phrases


def test_unavailable_client_falls_back() -> None:
    client = FakeClient([LLMUnavailable("down")])
    result = analyse("the total is wrong", load_graph(GOLDEN), client)
    assert result.route == "rules"
    assert result.fallback_reason is not None
    assert "unavailable" in result.fallback_reason
    assert result.intent.problem_type.value == "bug"


def test_active_file_is_appended_when_it_exists() -> None:
    payload = {
        "problem_type": "unknown",
        "observed": None,
        "expected": None,
        "key_phrases": ["hello"],
        "confidence": "low",
    }
    client = FakeClient([json.dumps(payload)])
    graph = load_graph(GOLDEN)
    result = analyse("hello there", graph, client, active_file="src/receipt.js")
    assert "src/receipt.js" in result.intent.files
    other = FakeClient([json.dumps(payload)])
    missing = analyse("hello there", graph, other, active_file="missing.js")
    assert "missing.js" not in missing.intent.files


def test_labelled_rules_match_the_shop_graph() -> None:
    graph = load_graph(GOLDEN)
    client = FakeClient([])
    for item in load_labelled(GOLDEN.parents[2] / "context" / "labelled_prompts.json"):
        if item.expected_route != "rules":
            continue
        result = analyse(item.question, graph, client)
        assert client.calls == []
        assert result.route == "rules"
        assert result.fallback_reason is None
        assert result.intent.problem_type.value == item.expected_problem_type
        assert set(result.intent.files) == set(item.expected_files)
        frames = {(frame.name, frame.file, frame.line) for frame in result.intent.frames}
        expected = {
            (str(frame["name"]), str(frame["file"]), int(frame["line"]))
            for frame in item.expected_frames
        }
        assert frames == expected


def test_evaluate_intents_with_fake_client() -> None:
    graph = load_graph(GOLDEN)
    items = [
        LabelledPrompt(
            question="explain `checkout`",
            expected_problem_type="explain",
            expected_key_phrases=[["checkout"]],
            expected_files=[],
            expected_frames=[],
            expected_route="rules",
        ),
        LabelledPrompt(
            question="the total is wrong",
            expected_problem_type="bug",
            expected_key_phrases=[["total"]],
            expected_files=[],
            expected_frames=[],
            expected_route="llm",
        ),
    ]
    client = FakeClient(
        [
            json.dumps(
                {
                    "problem_type": "bug",
                    "observed": "wrong total",
                    "expected": None,
                    "key_phrases": ["total"],
                    "confidence": "low",
                }
            )
        ]
    )
    report = evaluate_intents(items, graph, client)
    assert report.problem_type_accuracy == 1
    assert report.key_phrase_accuracy == 1
    assert report.file_accuracy == 1
    assert report.frame_accuracy == 1
    assert report.route_accuracy == 1
    assert report.qwen_calls == 1

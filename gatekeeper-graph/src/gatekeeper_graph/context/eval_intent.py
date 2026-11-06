"""Score intent classification against a labelled question file."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

from gatekeeper_graph.context.analyse import analyse
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.models import Graph


class LabelledPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    expected_problem_type: str
    expected_key_phrases: list[list[str]]
    expected_files: list[str]
    expected_frames: list[dict[str, str | int]]
    expected_route: Literal["llm", "rules"]


class IntentItemScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    problem_type: bool
    key_phrases: bool
    files: bool
    frames: bool
    route: bool
    latency_ms: float
    qwen_calls: int


class IntentEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[IntentItemScore, ...]
    problem_type_accuracy: float
    key_phrase_accuracy: float
    file_accuracy: float
    frame_accuracy: float
    route_accuracy: float
    qwen_calls: int

    def render(self) -> str:
        lines = [
            "# Intent evaluation",
            "",
            f"problem_type={self.problem_type_accuracy:.2f}",
            f"key_phrases={self.key_phrase_accuracy:.2f}",
            f"files={self.file_accuracy:.2f}",
            f"frames={self.frame_accuracy:.2f}",
            f"route={self.route_accuracy:.2f}",
            f"qwen_calls={self.qwen_calls}",
            "",
        ]
        for item in self.items:
            lines.append(
                f"- type={item.problem_type} phrases={item.key_phrases} "
                f"files={item.files} frames={item.frames} route={item.route} "
                f"ms={item.latency_ms:.1f} calls={item.qwen_calls} {item.question}"
            )
        lines.append("")
        return "\n".join(lines)


def load_labelled(path: Path) -> list[LabelledPrompt]:
    adapter = TypeAdapter(list[LabelledPrompt])
    return adapter.validate_json(path.read_text(encoding="utf-8"))


def evaluate_intents(
    items: list[LabelledPrompt],
    graph: Graph,
    client: LLMClient,
) -> IntentEvalReport:
    """Run analyse on each item and score the fields the label names."""
    scores: list[IntentItemScore] = []
    calls_before = _call_count(client)
    for item in items:
        started = time.perf_counter()
        before = _call_count(client)
        result = analyse(item.question, graph, client)
        after = _call_count(client)
        actual_frames = {(frame.name, frame.file, frame.line) for frame in result.intent.frames}
        expected_frames = {
            (str(frame.get("name", "")), str(frame["file"]), int(frame["line"]))
            for frame in item.expected_frames
        }
        blob = " ".join(result.intent.key_phrases)
        expected_phrases = [phrase for group in item.expected_key_phrases for phrase in group]
        scores.append(
            IntentItemScore(
                question=item.question,
                problem_type=result.intent.problem_type.value == item.expected_problem_type,
                key_phrases=_phrase_hit(blob, expected_phrases),
                files=set(result.intent.files) == set(item.expected_files),
                frames=actual_frames == expected_frames,
                route=result.route == item.expected_route,
                latency_ms=(time.perf_counter() - started) * 1000,
                qwen_calls=after - before,
            )
        )
    total = len(scores) or 1
    return IntentEvalReport(
        items=tuple(scores),
        problem_type_accuracy=sum(item.problem_type for item in scores) / total,
        key_phrase_accuracy=sum(item.key_phrases for item in scores) / total,
        file_accuracy=sum(item.files for item in scores) / total,
        frame_accuracy=sum(item.frames for item in scores) / total,
        route_accuracy=sum(item.route for item in scores) / total,
        qwen_calls=_call_count(client) - calls_before,
    )


def _phrase_hit(blob: str, expected: list[str]) -> bool:
    if not expected:
        return True
    return any(phrase in blob for phrase in expected)


def _call_count(client: LLMClient) -> int:
    calls = getattr(client, "calls", None)
    if isinstance(calls, list):
        return len(calls)
    return 0

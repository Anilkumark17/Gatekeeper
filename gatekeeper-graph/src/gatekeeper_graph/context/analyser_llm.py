"""Ask the configured model to classify a question. It never invents node ids."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gatekeeper_graph.context.intent import Confidence, Intent, ProblemType
from gatekeeper_graph.context.prepass import PrePass
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.llm.stats import CallStats

_SYSTEM = """You classify a software question. Reply with JSON only.
problem_type is one of bug, impact, change, explain, unknown.
bug: the program does the wrong thing or throws.
impact: the user asks what a change would affect or what depends on something.
change: the user wants code added, removed, renamed, or updated.
explain: the user wants to understand existing code.
unknown: none of the above.
key_phrases name the affected area in the user's own words,
such as "invoice", "city name", or "letter case".
Use 1 to 4 words per phrase, at most 6 phrases. Do not invent function names or file names.
observed and expected are short phrases, or null when the user did not say.
confidence is low, medium, or high.

Example question: the invoice prints the city in the wrong order
{"problem_type":"bug","observed":"city in the wrong order","expected":null,
"key_phrases":["invoice","city"],"confidence":"medium"}

Example question: how does the helper join the labels
{"problem_type":"explain","observed":null,"expected":null,"key_phrases":["helper","labels"],"confidence":"low"}
"""


class LlmIntentOut(BaseModel):
    """Schema sent to the model. Node ids are not fields."""

    model_config = ConfigDict(extra="forbid")

    problem_type: Literal["bug", "impact", "change", "explain", "unknown"]
    observed: str | None = None
    expected: str | None = None
    key_phrases: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]

    @field_validator("key_phrases")
    @classmethod
    def _limit(cls, value: list[str]) -> list[str]:
        return value[:6]


def analyse_llm(question: str, facts: PrePass, client: LLMClient) -> tuple[Intent, CallStats]:
    """Classify with the model and copy pre-pass files, frames, quotes, and names."""
    user = _user_prompt(question, facts)
    parsed, stats = client.generate_structured(_SYSTEM, user, LlmIntentOut)
    phrases = _phrases(parsed.key_phrases)
    intent = Intent(
        question=question,
        problem_type=ProblemType(parsed.problem_type),
        observed=_blank(parsed.observed),
        expected=_blank(parsed.expected),
        key_phrases=phrases,
        quoted_text=facts.quoted,
        backtick_names=facts.backticks,
        files=facts.files,
        frames=facts.frames,
        confidence=Confidence(parsed.confidence),
        source="llm",
    )
    return intent, stats


def _user_prompt(question: str, facts: PrePass) -> str:
    frames = ", ".join(f"{frame.name} {frame.file}:{frame.line}".strip() for frame in facts.frames)
    lines = [
        f"quoted: {', '.join(facts.quoted) if facts.quoted else 'none'}",
        f"files: {', '.join(facts.files) if facts.files else 'none'}",
        f"frames: {frames if frames else 'none'}",
        f"error_types: {', '.join(facts.error_types) if facts.error_types else 'none'}",
        "",
        "Question:",
        question,
    ]
    return "\n".join(lines)


def _phrases(raw: list[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for item in raw:
        phrase = " ".join(item.strip().lower().split())
        if not phrase or len(phrase.split(" ")) > 4 or phrase in cleaned:
            continue
        cleaned.append(phrase)
        if len(cleaned) == 6:
            break
    return tuple(cleaned)


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None

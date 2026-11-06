"""Keyword classification used when the question is explicit or the model is down."""

from __future__ import annotations

import re

from gatekeeper_graph.context.intent import Confidence, Intent, ProblemType
from gatekeeper_graph.context.prepass import PrePass

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "to",
        "and",
        "or",
        "for",
        "in",
        "on",
        "is",
        "it",
        "its",
        "at",
        "by",
        "with",
        "from",
        "as",
        "this",
        "that",
        "be",
        "are",
        "was",
        "were",
        "not",
        "but",
        "if",
        "then",
        "than",
        "too",
        "into",
        "over",
        "after",
        "before",
        "about",
        "when",
        "which",
        "who",
        "whom",
        "does",
        "do",
        "did",
        "can",
        "could",
        "should",
        "would",
        "please",
        "while",
        "each",
        "old",
    }
)

_KEYWORDS: tuple[tuple[ProblemType, tuple[str, ...]], ...] = (
    (ProblemType.IMPACT, ("break", "affect", "impact", "depends on", "uses")),
    (
        ProblemType.BUG,
        (
            "error",
            "wrong",
            "bug",
            "broken",
            "fail",
            "crash",
            "too high",
            "too low",
            "not working",
            "undefined",
            "null",
            "nan",
        ),
    ),
    (
        ProblemType.CHANGE,
        ("add", "create", "rename", "remove", "delete", "change", "update", "refactor"),
    ),
    (ProblemType.EXPLAIN, ("explain", "what", "how", "why", "where")),
)


def analyse_rules(question: str, facts: PrePass) -> Intent:
    """Classify from keywords and the pre-pass. Source is always rules."""
    problem = _problem_type(question, facts)
    phrases = _phrases(question, facts)
    confidence = (
        Confidence.HIGH if facts.backticks or facts.files or facts.frames else Confidence.LOW
    )
    return Intent(
        question=question,
        problem_type=problem,
        observed=None,
        expected=None,
        key_phrases=phrases,
        quoted_text=facts.quoted,
        backtick_names=facts.backticks,
        files=facts.files,
        frames=facts.frames,
        confidence=confidence,
        source="rules",
    )


def is_explicit(facts: PrePass, question: str) -> bool:
    """True when a name, file, or frame is present and the keyword type is known."""
    if not (facts.backticks or facts.files or facts.frames):
        return False
    return _problem_type(question, facts) is not ProblemType.UNKNOWN


def _problem_type(question: str, facts: PrePass) -> ProblemType:
    lowered = question.lower()
    for problem, words in _KEYWORDS:
        if problem is ProblemType.BUG and (facts.frames or facts.error_types):
            return ProblemType.BUG
        if any(_hit(lowered, word) for word in words):
            return problem
    return ProblemType.UNKNOWN


def _hit(question: str, word: str) -> bool:
    if " " in word:
        return word in question
    return re.search(rf"\b{re.escape(word)}\b", question) is not None


def _phrases(question: str, facts: PrePass) -> tuple[str, ...]:
    phrases: list[str] = []
    for name in facts.backticks:
        phrase = " ".join(name.strip().lower().split())
        if phrase and len(phrase.split(" ")) <= 4 and phrase not in phrases:
            phrases.append(phrase)
    content = 0
    for word in re.findall(r"[a-z0-9]+", question.lower()):
        if content >= 5 or len(phrases) >= 6:
            break
        if len(word) < 3 or word in _STOPWORDS or word in phrases:
            continue
        phrases.append(word)
        content += 1
    return tuple(phrases)

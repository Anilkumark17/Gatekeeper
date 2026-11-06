"""Choose anchors from the shortlist. Pinned rows stay. The model only picks numbers."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.intent import Confidence, Intent
from gatekeeper_graph.context.shortlist import Candidate
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.llm.stats import CallStats
from gatekeeper_graph.models import parse_node_id

logger = logging.getLogger(__name__)

_SOURCE_ORDER = ("frame", "backtick", "file", "quoted", "observed", "phrase")
_SYSTEM = """You pick the code items most likely involved in the problem.
Reply with JSON only. picks is a list of {n, reason}. n is a number from the list.
Choose at most 8. Do not invent numbers. Reasons are at most 15 words.
"""


class Pick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    reason: str

    @field_validator("reason")
    @classmethod
    def _short(cls, value: str) -> str:
        return " ".join(value.split()[:15])


class SelectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    picks: list[Pick] = Field(default_factory=list)

    @field_validator("picks")
    @classmethod
    def _cap(cls, value: list[Pick]) -> list[Pick]:
        return value[:8]


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    reason: str
    via: Literal["llm", "pinned", "score"]


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    anchors: tuple[Anchor, ...]
    stats: CallStats | None
    fallback_reason: str | None


def select(
    intent: Intent,
    candidates: list[Candidate],
    index: GraphIndex,
    client: LLMClient,
    route: Literal["llm", "rules"],
) -> Selection:
    """Ask the model which shortlist rows matter, unless the list is already decided."""
    skip = (
        len(candidates) <= 5
        or (bool(candidates) and all(item.pinned for item in candidates))
        or (route == "rules" and intent.confidence is Confidence.HIGH)
    )
    if skip:
        logger.info("select via=score reason=skip anchors=%s", len(candidates))
        return Selection(anchors=_by_score(candidates), stats=None, fallback_reason=None)
    try:
        prompt = _prompt(intent, candidates, index)
        parsed, stats = client.generate_structured(_SYSTEM, prompt, SelectionOut)
    except LLMUnavailable as exc:
        reason = f"llm unavailable: {exc}"
        logger.info("select via=score reason=%s", reason)
        return Selection(anchors=_by_score(candidates), stats=None, fallback_reason=reason)
    except LLMOutputInvalid as exc:
        reason = f"llm output invalid: {exc}"
        logger.info("select via=score reason=%s", reason)
        return Selection(anchors=_by_score(candidates), stats=None, fallback_reason=reason)
    anchors = _from_model(parsed, candidates)
    logger.info("select via=llm anchors=%s", len(anchors))
    return Selection(anchors=anchors, stats=stats, fallback_reason=None)


def _from_model(parsed: SelectionOut, candidates: list[Candidate]) -> tuple[Anchor, ...]:
    chosen: list[Anchor] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.pinned:
            continue
        chosen.append(_pinned(candidate))
        seen.add(candidate.node_id)
    used: set[int] = set()
    for pick in parsed.picks:
        if pick.n < 1 or pick.n > len(candidates) or pick.n in used:
            continue
        used.add(pick.n)
        candidate = candidates[pick.n - 1]
        if candidate.node_id in seen:
            continue
        seen.add(candidate.node_id)
        chosen.append(
            Anchor(node_id=candidate.node_id, reason=pick.reason or "selected", via="llm")
        )
    return tuple(chosen)


def _by_score(candidates: list[Candidate]) -> tuple[Anchor, ...]:
    pinned = [item for item in candidates if item.pinned]
    rest = [item for item in candidates if not item.pinned]
    chosen = list(pinned)
    if len(chosen) < 5:
        chosen.extend(rest[: 5 - len(chosen)])
    anchors: list[Anchor] = []
    for item in chosen:
        if item.pinned:
            anchors.append(_pinned(item))
        else:
            anchors.append(Anchor(node_id=item.node_id, reason="top search score", via="score"))
    return tuple(anchors)


def _pinned(candidate: Candidate) -> Anchor:
    reason = f"pinned by {_source(candidate.sources)}"
    return Anchor(node_id=candidate.node_id, reason=reason, via="pinned")


def _source(sources: frozenset[str]) -> str:
    for name in _SOURCE_ORDER:
        if name in sources:
            return name
    return sorted(sources)[0] if sources else "pin"


def _prompt(intent: Intent, candidates: list[Candidate], index: GraphIndex) -> str:
    lines = [
        f"problem_type: {intent.problem_type.value}",
        f"observed: {intent.observed or 'none'}",
        f"expected: {intent.expected or 'none'}",
        "items:",
    ]
    for number, candidate in enumerate(candidates, start=1):
        node = index.get(candidate.node_id)
        if node is None:
            lines.append(f"{number}. {candidate.node_id}")
            continue
        bare = parse_node_id(node.id)[2] or node.id
        start = node.range.start if node.range is not None else 1
        if node.summary:
            detail = node.summary
        else:
            params = ", ".join(node.signature.params) if node.signature.params else "none"
            detail = f"params: {params}"
        file = node.file or ""
        lines.append(f"{number}. {bare} ({node.kind.value}, {file}:{start}) - {detail}")
    return "\n".join(lines)

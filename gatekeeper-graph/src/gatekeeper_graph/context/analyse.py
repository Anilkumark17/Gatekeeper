"""Route a question to the model or to the keyword rules."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.context.analyser_llm import analyse_llm
from gatekeeper_graph.context.analyser_rules import analyse_rules, is_explicit
from gatekeeper_graph.context.intent import Intent
from gatekeeper_graph.context.prepass import PrePass, prepass
from gatekeeper_graph.llm.base import LLMClient
from gatekeeper_graph.llm.errors import LLMOutputInvalid, LLMUnavailable
from gatekeeper_graph.llm.stats import CallStats
from gatekeeper_graph.models import Graph, NodeKind

logger = logging.getLogger(__name__)


class AnalyseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Intent
    prepass: PrePass
    route: Literal["llm", "rules"]
    stats: CallStats | None
    fallback_reason: str | None


def analyse(
    question: str,
    graph: Graph,
    client: LLMClient,
    active_file: str | None = None,
) -> AnalyseResult:
    """Pre-pass, then rules for an explicit question, otherwise the model with a rules fallback."""
    facts = prepass(question, _file_ids(graph))
    if is_explicit(facts, question):
        result = AnalyseResult(
            intent=_with_active(analyse_rules(question, facts), graph, active_file),
            prepass=facts,
            route="rules",
            stats=None,
            fallback_reason=None,
        )
        logger.info("analyse route=rules fallback=none")
        return result
    try:
        intent, stats = analyse_llm(question, facts, client)
    except LLMUnavailable as exc:
        return _fallback(question, facts, graph, active_file, f"llm unavailable: {exc}")
    except LLMOutputInvalid as exc:
        return _fallback(question, facts, graph, active_file, f"llm output invalid: {exc}")
    result = AnalyseResult(
        intent=_with_active(intent, graph, active_file),
        prepass=facts,
        route="llm",
        stats=stats,
        fallback_reason=None,
    )
    logger.info("analyse route=llm fallback=none")
    return result


def _fallback(
    question: str,
    facts: PrePass,
    graph: Graph,
    active_file: str | None,
    reason: str,
) -> AnalyseResult:
    logger.info("analyse route=rules fallback=%s", reason)
    return AnalyseResult(
        intent=_with_active(analyse_rules(question, facts), graph, active_file),
        prepass=facts,
        route="rules",
        stats=None,
        fallback_reason=reason,
    )


def _file_ids(graph: Graph) -> frozenset[str]:
    return frozenset(node.id for node in graph.nodes.values() if node.kind is NodeKind.FILE)


def _with_active(intent: Intent, graph: Graph, active_file: str | None) -> Intent:
    if active_file is None:
        return intent
    files = _file_ids(graph)
    if active_file not in files or active_file in intent.files:
        return intent
    merged = tuple(sorted({*intent.files, active_file}))
    return intent.model_copy(update={"files": merged})

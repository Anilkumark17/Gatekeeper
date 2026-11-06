"""Pinned names and search hits, capped without dropping pins."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.intent import Intent
from gatekeeper_graph.context.search import SearchIndex


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    score: float
    sources: frozenset[str]
    pinned: bool


def build_shortlist(
    intent: Intent,
    index: GraphIndex,
    search: SearchIndex,
    k: int = 25,
) -> list[Candidate]:
    """Pin backticks, frames, and small files, then merge search hits."""
    pinned: dict[str, set[str]] = {}
    loose: dict[str, set[str]] = {}
    scores: dict[str, float] = {}

    def pin(node_id: str, source: str) -> None:
        pinned.setdefault(node_id, set()).add(source)
        scores[node_id] = 1.0

    for name in intent.backtick_names:
        for node_id in index.exact(name):
            pin(node_id, "backtick")
    for frame in intent.frames:
        node = index.node_at(frame.file, frame.line)
        if node is not None:
            pin(node.id, "frame")
    for file in intent.files:
        symbols = index.symbols_in_file(file)
        if len(symbols) > 8:
            pin(file, "file")
            for symbol in symbols:
                loose.setdefault(symbol.id, set()).add("file")
                scores.setdefault(symbol.id, 0.0)
        else:
            for symbol in symbols:
                pin(symbol.id, "file")

    queries: list[tuple[str, str]] = [(phrase, "phrase") for phrase in intent.key_phrases]
    queries.extend((text, "quoted") for text in intent.quoted_text)
    if intent.observed:
        queries.append((intent.observed, "observed"))
    for text, source in queries:
        hits = search.search(text)
        if not hits:
            continue
        top = hits[0].score or 1.0
        for hit in hits:
            if hit.node_id in pinned:
                pinned[hit.node_id].add(source)
                continue
            normalized = hit.score / top
            scores[hit.node_id] = max(scores.get(hit.node_id, 0.0), normalized)
            loose.setdefault(hit.node_id, set()).add(source)

    pinned_ids = sorted(pinned)
    searched_ids = sorted(
        (node_id for node_id in scores if node_id not in pinned),
        key=lambda node_id: (-scores[node_id], node_id),
    )
    candidates = [
        Candidate(node_id=node_id, score=1.0, sources=frozenset(pinned[node_id]), pinned=True)
        for node_id in pinned_ids
    ]
    limit = max(k, len(candidates))
    for node_id in searched_ids:
        if len(candidates) >= limit:
            break
        candidates.append(
            Candidate(
                node_id=node_id,
                score=scores[node_id],
                sources=frozenset(loose.get(node_id, set())),
                pinned=False,
            )
        )
    return candidates
